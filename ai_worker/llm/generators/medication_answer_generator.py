import hashlib
import re
from typing import Any, Protocol

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.chains.medication_answer_chain import (
    MedicationAnswerChainInput,
    build_medication_answer_chain,
)
from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.llm.prompts.medication_chat_prompt import (
    MEDICATION_CHAT_PROMPT_VERSION,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationAnswerFallbackReason,
    MedicationAnswerGenerationObservation,
    MedicationAnswerGenerationOutcome,
    MedicationAnswerPayload,
    MedicationAnswerRewriteStatus,
    MedicationChatReasonCode,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRiskScope,
    MedicationChatRoute,
    MedicationChatSourceKind,
)


class AsyncMedicationAnswerClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> MedicationAnswerPayload | dict[str, Any]: ...


class OpenAIMedicationAnswerGenerator:
    _GENERAL_SUPPLEMENT_GUIDANCE_REASON_CODE = "GENERAL_SUPPLEMENT_GUIDANCE"
    _LLM_REWRITE_SOURCE_KINDS = frozenset(
        {
            MedicationChatSourceKind.MEDICATION_GUIDE,
            MedicationChatSourceKind.INTERACTION_RULE,
            MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
        }
    )
    _DOSAGE_TOKEN_PATTERN = re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|μg|㎍|g|mL|ml|정|캡슐|포|회|일|시간|%)",
        re.IGNORECASE,
    )
    _SAFETY_ASSERTION_PATTERN = re.compile(
        r"(?:안전|문제\s*없|괜찮)[^.!?。！？]{0,12}(?:합니다|해요|습니다)|"
        r"(?:상호작용|부작용)(?:이|은|는)?\s*없(?:습니다|어요)",
        re.IGNORECASE,
    )
    _MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s*")
    _SECTION_HEADER_PATTERN = re.compile(r"^\s*(?P<icon>✅|⚠️|🚫|💊|💪🏻)\s*\*\*(?P<title>[^*\n]+)\*\*\s*:?\s*$")
    _BOLD_MARKER_PATTERN = re.compile(r"\*\*(.+?)\*\*")
    _BULLET_MARKER_PATTERN = re.compile(r"^\s*(?:[-*•])\s*")
    _SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
    _DISCLAIMER_PATTERN = re.compile(r"의료\s*(?:전문가|진)의\s*(?:진단|진료|처방).*대체하지\s*않습니다")
    _INTERACTION_SECTION_TITLE = "상호작용"

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncMedicationAnswerClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        self._model_name = normalized_model
        response_runnable: Runnable
        if client is not None:
            response_runnable = RunnableLambda(client.ainvoke).with_config(
                run_name="medication.answer.client",
            )
        else:
            chat_model = ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            response_runnable = chat_model.with_structured_output(
                MedicationAnswerPayload,
                method="json_schema",
                strict=True,
            ).with_config(run_name="medication.answer.model")
        self._chain = build_medication_answer_chain(
            response_runnable=response_runnable,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        draft_hash = self._answer_hash(result.answer)
        if result.route == MedicationChatRoute.CLARIFICATION:
            return self._skipped_outcome(
                result,
                draft_hash=draft_hash,
                reason=MedicationAnswerFallbackReason.CLARIFICATION_REQUIRED,
            )
        if not result.sources and not self._allows_no_source_llm_guidance(result):
            return self._skipped_outcome(
                result,
                draft_hash=draft_hash,
                reason=MedicationAnswerFallbackReason.NO_GROUNDED_SOURCES,
            )
        if not self._has_external_rewrite_evidence(result) and not self._allows_no_source_llm_guidance(result):
            return self._skipped_outcome(
                result,
                draft_hash=draft_hash,
                reason=MedicationAnswerFallbackReason.PATIENT_CONTEXT_ONLY,
            )
        try:
            payload = await self._chain.ainvoke(
                MedicationAnswerChainInput(
                    request=request,
                    context=context,
                    result=result,
                ),
                config={
                    "metadata": {
                        "model_name": self._model_name,
                        "prompt_version": MEDICATION_CHAT_PROMPT_VERSION,
                        "route": result.route.value,
                        "source_count": len(result.sources),
                        "covered_section_count": (
                            len(result.evidence_coverage.covered_section_types)
                            if result.evidence_coverage is not None
                            else 0
                        ),
                    }
                },
            )
        except Exception as error:
            raise ChatAnswerGenerationError(
                "약·영양제 챗봇 답변 생성에 실패했습니다.",
                reason_code=MedicationAnswerFallbackReason.CLIENT_ERROR.value,
            ) from error
        generated_answer = self._to_limited_markdown(payload.answer)
        generated_hash = self._answer_hash(generated_answer)
        fallback_reason = self._grounding_failure_reason(
            draft_answer=result.answer,
            generated_answer=generated_answer,
            declared_section_types=payload.section_types,
            covered_section_types=(
                result.evidence_coverage.covered_section_types if result.evidence_coverage is not None else None
            ),
        )
        if fallback_reason is not None:
            fallback_result = result.model_copy(
                update={
                    "model_name": self._model_name,
                    "prompt_version": MEDICATION_CHAT_PROMPT_VERSION,
                },
            )
            return MedicationAnswerGenerationOutcome(
                result=fallback_result,
                observation=MedicationAnswerGenerationObservation(
                    status=MedicationAnswerRewriteStatus.DRAFT_FALLBACK,
                    fallback_used=True,
                    fallback_reason=fallback_reason,
                    declared_section_types=payload.section_types,
                    draft_answer_hash=draft_hash,
                    generated_answer_hash=generated_hash,
                ),
            )
        rewritten = result.model_copy(
            update={
                "answer": generated_answer,
                "model_name": self._model_name,
                "prompt_version": MEDICATION_CHAT_PROMPT_VERSION,
            },
        )
        return MedicationAnswerGenerationOutcome(
            result=rewritten,
            observation=MedicationAnswerGenerationObservation(
                status=MedicationAnswerRewriteStatus.REWRITTEN,
                fallback_used=False,
                declared_section_types=payload.section_types,
                draft_answer_hash=draft_hash,
                generated_answer_hash=generated_hash,
            ),
        )

    @classmethod
    def _grounding_failure_reason(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
        declared_section_types: list[KnowledgeSectionType] | None = None,
        covered_section_types: list[KnowledgeSectionType] | None = None,
    ) -> MedicationAnswerFallbackReason | None:
        if covered_section_types is not None and not set(
            declared_section_types or [],
        ).issubset(covered_section_types):
            return MedicationAnswerFallbackReason.UNSUPPORTED_EVIDENCE_SECTION
        if cls._SAFETY_ASSERTION_PATTERN.search(generated_answer) and not cls._SAFETY_ASSERTION_PATTERN.search(
            draft_answer
        ):
            return MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION
        draft_dosages = {token.casefold().replace(" ", "") for token in cls._DOSAGE_TOKEN_PATTERN.findall(draft_answer)}
        generated_dosages = {
            token.casefold().replace(" ", "") for token in cls._DOSAGE_TOKEN_PATTERN.findall(generated_answer)
        }
        if not generated_dosages.issubset(draft_dosages):
            return MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT
        return None

    @staticmethod
    def _answer_hash(answer: str) -> str:
        return hashlib.sha256(answer.strip().encode("utf-8")).hexdigest()

    @classmethod
    def _has_external_rewrite_evidence(cls, result: MedicationChatResult) -> bool:
        """등록 정보는 답변 대상을 식별할 뿐, 의학적 주장의 근거가 되지 않는다."""

        return any(source.kind in cls._LLM_REWRITE_SOURCE_KINDS for source in result.sources)

    @staticmethod
    def _is_evidence_gap_guidance(result: MedicationChatResult) -> bool:
        """근거 부재 안내는 새 의학 주장을 만들지 않는 범위에서만 LLM이 정리한다."""

        return (
            MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value
            in result.safety_reason_codes
        )

    @classmethod
    def _allows_no_source_llm_guidance(cls, result: MedicationChatResult) -> bool:
        """근거 부재 안내와 저위험 일반 영양 안내만 출처 없이 LLM 정리를 허용한다."""

        return cls._is_evidence_gap_guidance(result) or (
            cls._GENERAL_SUPPLEMENT_GUIDANCE_REASON_CODE in result.safety_reason_codes
            and result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
            and result.risk_decision is not None
            and result.risk_decision.scope == MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE
        )

    @staticmethod
    def _skipped_outcome(
        result: MedicationChatResult,
        *,
        draft_hash: str,
        reason: MedicationAnswerFallbackReason,
    ) -> MedicationAnswerGenerationOutcome:
        return MedicationAnswerGenerationOutcome(
            result=result,
            observation=MedicationAnswerGenerationObservation(
                status=MedicationAnswerRewriteStatus.SKIPPED,
                fallback_used=False,
                fallback_reason=reason,
                draft_answer_hash=draft_hash,
            ),
        )

    @classmethod
    def _to_limited_markdown(cls, answer: str) -> str:
        """답변에서는 체크 표시가 붙은 소제목 강조와 목록만 허용한다."""

        normalized_lines: list[str] = []
        interaction_lines: list[str] | None = None
        for line in answer.splitlines():
            line = cls._MARKDOWN_HEADING_PATTERN.sub("", line)
            section_header = cls._SECTION_HEADER_PATTERN.fullmatch(line)
            if section_header is not None and interaction_lines is not None:
                normalized_lines.extend(cls._format_interaction_section(interaction_lines))
                interaction_lines = None
            if section_header is not None:
                icon = section_header.group("icon")
                title = section_header.group("title").strip()
                normalized_lines.append(f"{icon} **{title}**")
                if cls._INTERACTION_SECTION_TITLE in title:
                    interaction_lines = []
                continue
            if interaction_lines is not None:
                if cls._DISCLAIMER_PATTERN.search(line):
                    normalized_lines.extend(cls._format_interaction_section(interaction_lines))
                    interaction_lines = None
                else:
                    interaction_lines.append(line)
                    continue
            line = cls._BOLD_MARKER_PATTERN.sub(r"\1", line)
            line = re.sub(r"__(.+?)__", r"\1", line)
            normalized_lines.append(line)
        if interaction_lines is not None:
            normalized_lines.extend(cls._format_interaction_section(interaction_lines))
        return "\n".join(normalized_lines).strip()

    @classmethod
    def _format_interaction_section(cls, lines: list[str]) -> list[str]:
        """상호작용 사실을 줄글 대신 대시 목록으로 고정한다."""

        prose_lines: list[str] = []
        bullet_items: list[list[str]] = []
        current_bullet: list[str] | None = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            bullet_match = cls._BULLET_MARKER_PATTERN.match(line)
            if bullet_match is not None:
                if current_bullet is not None:
                    bullet_items.append(current_bullet)
                current_bullet = [line[bullet_match.end() :]]
                continue
            if current_bullet is not None:
                current_bullet.append(line)
            else:
                prose_lines.append(line)

        if current_bullet is not None:
            bullet_items.append(current_bullet)

        facts = cls._interaction_sentences(prose_lines)
        facts.extend(cls._normalize_interaction_fact(item) for item in bullet_items)
        facts = [fact for fact in facts if fact]
        if not facts:
            return []
        return ["", *(f"- {fact}" for fact in facts)]

    @classmethod
    def _interaction_sentences(cls, lines: list[str]) -> list[str]:
        prose = cls._normalize_interaction_fact(lines)
        if not prose:
            return []
        return [
            cls._normalize_interaction_fact([sentence])
            for sentence in cls._SENTENCE_BOUNDARY_PATTERN.split(prose)
            if sentence.strip()
        ]

    @classmethod
    def _normalize_interaction_fact(cls, lines: list[str]) -> str:
        text = " ".join(line.strip() for line in lines if line.strip())
        text = cls._BULLET_MARKER_PATTERN.sub("", text)
        text = cls._BOLD_MARKER_PATTERN.sub(r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        return re.sub(r"\s+", " ", text).strip()
