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
from ai_worker.safety.grounded_claim_validator import RuleBasedGroundedClaimValidator
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
    # 단위 집합은 프롬프트의 용량 가림 패턴과 같아야 한다. 여기에만 없는 단위가 있으면
    # 그 단위의 환각 용량(예: `5,000IU` → `10,000IU`)을 검증이 놓친다.
    _DOSAGE_TOKEN_PATTERN = re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|μg|㎍|g|mL|ml|IU|mEq|밀리그램|그램|밀리리터|국제단위|정|캡슐|포|회|일|시간|%)",
        re.IGNORECASE,
    )
    # 공식 경고문에서 지시 문장만 떼어내기 위한 경계. 원문은 띄어쓰기가 없을 수 있다.
    _OFFICIAL_SENTENCE_BOUNDARY = re.compile(r"(?<=[다요오])\.\s*")
    _SAFETY_ASSERTION_PATTERN = re.compile(
        r"(?:안전|문제\s*없|괜찮)[^.!?。！？]{0,12}(?:합니다|해요|습니다)|"
        r"(?:상호작용|부작용)(?:이|은|는)?\s*없(?:습니다|어요)",
        re.IGNORECASE,
    )
    _MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s*")
    _SECTION_HEADER_PATTERN = re.compile(
        r"^\s*(?P<icon>✅|⚠️|🚨|🚫|💊|💪🏻|🔁|🩻|✉️|📭|🧬|🍗)\s*\*\*(?P<title>[^*\n]+)\*\*"
        r"(?:\s+(?P<subtitle>\*\*(?:주의가 필요한 조합|참고할 상호작용|도움이 확인된 조합)\*\*))?\s*:?\s*$"
    )
    _STANDALONE_BOLD_LINE_PATTERN = re.compile(r"^\s*\*\*(?P<value>[^*\n]+)\*\*\s*$")
    _BOLD_MARKER_PATTERN = re.compile(r"\*\*(.+?)\*\*")
    _INTERACTION_PAIR_HEADER_PATTERN = re.compile(r"^\*\*(?P<pair>\[[^\]\n]+\])\*\*$")
    _BULLET_MARKER_PATTERN = re.compile(r"^\s*(?:[-*•])\s*")
    _SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
    _DISCLAIMER_PATTERN = re.compile(r"의료\s*(?:전문가|진)의\s*(?:진단|진료|처방).*대체하지\s*않습니다")
    _INTERACTION_SECTION_TITLE = "상호작용"
    _QUESTION_INTERACTION_HEADER = "🔁 **질문 상호작용**"
    _INTERACTION_OVERVIEW_HEADERS = ("🧬 **약과 상호작용**", "🍗 **그 외 상호작용**")
    _MISSING_EVIDENCE_LINE_PATTERN = re.compile(r"확인하지\s*못|(?:근거|자료|정보)[^.!?\n]{0,30}없")
    _CAUTION_SECTION_HEADER = "⚠️ **주의사항**"
    _MAX_BULLET_EOJEOLS = 10
    _MAX_BULLET_CHARACTERS = 100
    _MAX_COMPACT_ANSWER_CHARACTERS = 1_200

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncMedicationAnswerClient | None = None,
        accurate_model: str | None = None,
        accurate_client: AsyncMedicationAnswerClient | None = None,
        high_accuracy_routing_enabled: bool = False,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        self._model_name = normalized_model
        self._accurate_model_name: str | None = None
        self._accurate_chain: Runnable | None = None
        self._high_accuracy_routing_enabled = high_accuracy_routing_enabled
        self._chain = self._build_chain(
            model_name=normalized_model,
            api_key=api_key,
            client=client,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            run_name_prefix="medication.answer",
        )
        normalized_accurate_model = (accurate_model or "").strip()
        if (
            high_accuracy_routing_enabled
            and normalized_accurate_model
            and normalized_accurate_model != normalized_model
        ):
            # 테스트에서 fast client만 주어진 경우 상위 모델을 흉내 내지 않는다.
            # 런타임에서는 client가 없으므로 별도 ChatOpenAI 체인이 만들어진다.
            if client is None or accurate_client is not None:
                self._accurate_model_name = normalized_accurate_model
                self._accurate_chain = self._build_chain(
                    model_name=normalized_accurate_model,
                    api_key=api_key,
                    client=accurate_client,
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                    run_name_prefix="medication.answer.accurate",
                )

    @staticmethod
    def _build_chain(
        *,
        model_name: str,
        api_key: SecretStr | None,
        client: AsyncMedicationAnswerClient | None,
        timeout_seconds: float,
        max_retries: int,
        run_name_prefix: str,
    ) -> Runnable:
        response_runnable: Runnable
        if client is not None:
            response_runnable = RunnableLambda(client.ainvoke).with_config(
                run_name=f"{run_name_prefix}.client",
            )
        else:
            chat_model = ChatOpenAI(
                model=model_name,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            response_runnable = chat_model.with_structured_output(
                MedicationAnswerPayload,
                method="json_schema",
                strict=True,
            ).with_config(run_name=f"{run_name_prefix}.model")
        return build_medication_answer_chain(
            response_runnable=response_runnable,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    def _chain_for_result(
        self,
        result: MedicationChatResult,
    ) -> tuple[Runnable, str]:
        requested_sections = set(
            result.evidence_coverage.requested_section_types if result.evidence_coverage is not None else []
        )
        if (
            self._high_accuracy_routing_enabled
            and self._accurate_chain is not None
            and self._accurate_model_name is not None
            and (KnowledgeSectionType.INTERACTION in requested_sections or len(requested_sections) > 1)
        ):
            return self._accurate_chain, self._accurate_model_name
        return self._chain, self._model_name

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
        chain, selected_model_name = self._chain_for_result(result)
        covered_section_types = (
            result.evidence_coverage.covered_section_types if result.evidence_coverage is not None else None
        )
        compacted_adverse_case_report = False
        try:
            payload = await self._invoke_chain(
                chain=chain,
                request=request,
                context=context,
                result=result,
                selected_model_name=selected_model_name,
            )
            generated_answer = self._format_generated_answer(
                draft_answer=result.answer,
                generated_answer=payload.answer,
            )
            grounding_failure = self._grounding_failure_reason(
                draft_answer=result.answer,
                generated_answer=generated_answer,
                declared_section_types=payload.section_types,
                covered_section_types=covered_section_types,
            )
            # 짧은 요약이어도 섹션 선언이 틀리면 한 번 보정한다.
            # 최종 근거 검증은 그대로 유지하며, 형식 보정과 호출 예산을 공유한다.
            if self._requires_format_repair(generated_answer) or grounding_failure in {
                MedicationAnswerFallbackReason.UNSUPPORTED_EVIDENCE_SECTION,
                MedicationAnswerFallbackReason.OMITTED_EVIDENCE_SECTION,
            }:
                payload = await self._invoke_chain(
                    chain=chain,
                    request=request,
                    context=context,
                    result=result,
                    selected_model_name=selected_model_name,
                    format_repair_answer=generated_answer,
                )
                generated_answer = self._format_generated_answer(
                    draft_answer=result.answer,
                    generated_answer=payload.answer,
                )
                unrepaired_answer = generated_answer
                generated_answer = self._compact_unrepaired_adverse_case_report(
                    draft_answer=result.answer,
                    answer=generated_answer,
                )
                compacted_adverse_case_report = generated_answer != unrepaired_answer
        except Exception as error:
            raise ChatAnswerGenerationError(
                "약·영양제 챗봇 답변 생성에 실패했습니다.",
                reason_code=MedicationAnswerFallbackReason.CLIENT_ERROR.value,
            ) from error
        # 공식 경고문을 지키려고 초안을 되돌린 경우도 초안이 그대로 나간 것이다.
        # 상태를 재작성 성공으로 남기면 초안 노출률이 실제보다 낮게 집계된다.
        preserved_official_warning = self._must_preserve_official_warning(
            context=context,
            result=result,
            generated_answer=generated_answer,
        )
        if preserved_official_warning:
            generated_answer = self._with_official_warning_restored(
                result=result,
                generated_answer=generated_answer,
            )
        generated_hash = self._answer_hash(generated_answer)
        fallback_reason = (
            MedicationAnswerFallbackReason.OFFICIAL_WARNING_PRESERVED
            if preserved_official_warning
            else self._grounding_failure_reason(
                draft_answer=result.answer,
                generated_answer=generated_answer,
                declared_section_types=payload.section_types,
                covered_section_types=covered_section_types,
                allow_uncovered_adverse_case_report=compacted_adverse_case_report,
            )
        )
        if fallback_reason is not None:
            fallback_answer = self._compact_unrepaired_adverse_case_report(
                draft_answer=result.answer,
                answer=result.answer,
            )
            fallback_result = result.model_copy(
                update={
                    "answer": fallback_answer,
                    "model_name": selected_model_name,
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
                "model_name": selected_model_name,
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
    def _with_official_warning_restored(
        cls,
        *,
        result: MedicationChatResult,
        generated_answer: str,
    ) -> str:
        """재서술된 복약 변경 지시만 공식 원문 문장으로 되돌린다.

        답변 전체를 초안으로 바꾸면 요약이 모두 사라지고 가공되지 않은 원문이 나간다.
        지시 문장만 원문으로 두면 경고 문구는 한 글자도 바뀌지 않으면서
        나머지 주의사항은 요약을 유지한다. 대응 원문을 찾지 못하면 기존처럼 초안을 쓴다.
        """

        official_sentences = [
            sentence.strip()
            for text in result.official_warning_texts
            for sentence in cls._OFFICIAL_SENTENCE_BOUNDARY.split(text)
            if sentence.strip() and RuleBasedGroundedClaimValidator.contains_medication_change_instruction(sentence)
        ]
        if not official_sentences:
            return result.answer

        restored: list[str] = []
        replaced = 0
        for line in generated_answer.splitlines():
            if (
                line.lstrip().startswith("- ")
                and replaced < len(official_sentences)
                and RuleBasedGroundedClaimValidator.contains_medication_change_instruction(line)
            ):
                restored.append(f"- {official_sentences[replaced]}")
                replaced += 1
            else:
                restored.append(line)
        return "\n".join(restored) if replaced else result.answer

    @staticmethod
    def _must_preserve_official_warning(
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
        generated_answer: str,
    ) -> bool:
        """공식 중단 경고를 LLM이 바꾸면 원문 초안으로 되돌린다."""

        if not result.official_warning_texts:
            return False
        diagnostic = RuleBasedGroundedClaimValidator().diagnose(
            context=context,
            result=result.model_copy(update={"answer": generated_answer}),
        )
        return diagnostic.rule_code == "MEDICATION_CHANGE_INSTRUCTION"

    @staticmethod
    def _generation_metadata(
        *,
        result: MedicationChatResult,
        selected_model_name: str,
    ) -> dict[str, object]:
        return {
            "model_name": selected_model_name,
            "prompt_version": MEDICATION_CHAT_PROMPT_VERSION,
            "route": result.route.value,
            "source_count": len(result.sources),
            "covered_section_count": (
                len(result.evidence_coverage.covered_section_types) if result.evidence_coverage is not None else 0
            ),
        }

    async def _invoke_chain(
        self,
        *,
        chain: Runnable,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
        selected_model_name: str,
        format_repair_answer: str | None = None,
    ) -> MedicationAnswerPayload:
        return await chain.ainvoke(
            MedicationAnswerChainInput(
                request=request,
                context=context,
                result=result,
                format_repair_answer=format_repair_answer,
            ),
            config={
                "metadata": self._generation_metadata(
                    result=result,
                    selected_model_name=selected_model_name,
                )
            },
        )

    @classmethod
    def _format_generated_answer(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
    ) -> str:
        return cls._to_limited_markdown(
            cls._restore_required_response_subject(
                draft_answer=draft_answer,
                generated_answer=cls._restore_required_formulation_cautions(
                    draft_answer=draft_answer,
                    generated_answer=cls._restore_required_question_interaction_pairs(
                        draft_answer=draft_answer,
                        generated_answer=generated_answer,
                    ),
                ),
            )
        )

    @classmethod
    def _restore_required_response_subject(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
    ) -> str:
        """근거 초안의 단일 제품·성분 제목을 LLM이 빼면 다시 붙인다."""

        draft_subject = cls._leading_standalone_subject(draft_answer)
        if draft_subject is None:
            return generated_answer
        if any(line.strip() == f"**{draft_subject}**" for line in generated_answer.splitlines()):
            return generated_answer
        return "\n\n".join((f"**{draft_subject}**", generated_answer.strip()))

    @classmethod
    def _leading_standalone_subject(cls, answer: str) -> str | None:
        """답변 첫 블록에 독립 제목으로 적힌 제품·성분명만 식별한다."""

        for raw_line in answer.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if match := cls._STANDALONE_BOLD_LINE_PATTERN.fullmatch(line):
                value = match.group("value").strip()
                if not cls._INTERACTION_PAIR_HEADER_PATTERN.fullmatch(line):
                    return value
            return None
        return None

    @classmethod
    def _requires_format_repair(cls, answer: str) -> bool:
        """휴대폰용 답변 규약을 벗어난 경우에만 한 번 더 압축한다."""

        if len(answer) > cls._MAX_COMPACT_ANSWER_CHARACTERS:
            return True
        bullet_parts: list[str] = []
        current_bullet: list[str] | None = None
        for raw_line in answer.splitlines():
            line = raw_line.strip()
            if cls._BULLET_MARKER_PATTERN.match(line):
                if current_bullet is not None:
                    bullet_parts.append(" ".join(current_bullet))
                current_bullet = [cls._BULLET_MARKER_PATTERN.sub("", line).strip()]
            elif current_bullet is not None and line and not cls._SECTION_HEADER_PATTERN.fullmatch(line):
                current_bullet.append(line)
        if current_bullet is not None:
            bullet_parts.append(" ".join(current_bullet))
        return any(
            len(part) > cls._MAX_BULLET_CHARACTERS or len(part.split()) > cls._MAX_BULLET_EOJEOLS
            for part in bullet_parts
        )

    @classmethod
    def _compact_unrepaired_adverse_case_report(
        cls,
        *,
        draft_answer: str,
        answer: str,
    ) -> str:
        """두 번째 생성도 장문이면 이상사례의 검증된 핵심만 안전하게 남긴다."""

        answer = cls._normalize_adverse_report_headers(answer)
        if (
            not cls._requires_format_repair(answer)
            or not cls._is_adverse_case_report(draft_answer)
            or not cls._is_adverse_case_report(answer)
        ):
            return answer

        event_lines, detail_lines = cls._adverse_report_lines(answer)
        event = cls._compact_adverse_event(event_lines)
        detail = cls._compact_adverse_detail(detail_lines)
        if event is None:
            return answer

        sections = [
            "🩻 **부작용 리포트**",
            "**이상사례**\n- " + event,
        ]
        if detail is not None:
            sections.append("**추가설명**\n- " + detail)
        return "\n\n".join(sections)

    @staticmethod
    def _normalize_adverse_report_headers(answer: str) -> str:
        """이전 초안도 새 리포트 제목으로 표시하되 다른 답변은 유지한다."""

        aliases = {
            "🩻 **부작용 보고서**": "🩻 **부작용 리포트**",
            "**상세 사항**": "**추가설명**",
        }
        lines = answer.splitlines()
        if not any(line.strip() in {"🩻 **부작용 보고서**", "🩻 **부작용 리포트**"} for line in lines):
            return answer
        return "\n".join(aliases.get(line.strip(), line) for line in lines)

    @classmethod
    def _is_adverse_case_report(cls, answer: str) -> bool:
        """초안과 생성 답변 모두가 사례 보고서 형식인지 확인한다."""

        headers = {line.strip() for line in cls._normalize_adverse_report_headers(answer).splitlines()}
        return {"🩻 **부작용 리포트**", "**이상사례**", "**추가설명**"}.issubset(headers)

    @classmethod
    def _adverse_report_lines(cls, answer: str) -> tuple[list[str], list[str]]:
        event_lines: list[str] = []
        detail_lines: list[str] = []
        section: list[str] | None = None
        for raw_line in answer.splitlines():
            line = raw_line.strip()
            if line == "**이상사례**":
                section = event_lines
                continue
            if line in {"**상세 사항**", "**추가설명**"}:
                section = detail_lines
                continue
            if section is not None and line:
                section.append(cls._BULLET_MARKER_PATTERN.sub("", line).strip())
        return event_lines, detail_lines

    @staticmethod
    def _compact_adverse_event(lines: list[str]) -> str | None:
        text = " ".join(lines).strip()
        if not text:
            return None
        text = re.sub(r"^\s*\d+\)\s*이상사례\s*[:：]\s*", "", text)
        text = re.sub(r"^\s*이상사례\s*[:：]\s*", "", text)
        event = re.split(r"[,.→]", text, maxsplit=1)[0].strip()
        event = re.sub(r"\s*\([^)]*\)", "", event).strip()
        return f"{event}이 보고됨." if event else None

    @staticmethod
    def _compact_adverse_detail(lines: list[str]) -> str | None:
        text = " ".join(lines).strip()
        if not text:
            return None
        if "WHO-UMC" in text and re.search(r"상당히\s*확실함['\"’”]?\s*(?:입니다|으로\s*(?:평가|분류))", text):
            return "WHO-UMC 평가에서 상당히 확실함으로 분류됨."
        if "시간적 연관" in text or "시간적 관련" in text:
            return "약물 복용과 증상 발생의 시간적 관계를 검토함."
        return None

    @classmethod
    def _grounding_failure_reason(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
        declared_section_types: list[KnowledgeSectionType] | None = None,
        covered_section_types: list[KnowledgeSectionType] | None = None,
        allow_uncovered_adverse_case_report: bool = False,
    ) -> MedicationAnswerFallbackReason | None:
        if (
            not allow_uncovered_adverse_case_report
            and covered_section_types is not None
            and not set(declared_section_types or []).issubset(covered_section_types)
        ):
            return MedicationAnswerFallbackReason.UNSUPPORTED_EVIDENCE_SECTION
        if cls._omits_interaction_overview(draft_answer=draft_answer, generated_answer=generated_answer):
            return MedicationAnswerFallbackReason.OMITTED_EVIDENCE_SECTION
        if cls._SAFETY_ASSERTION_PATTERN.search(generated_answer) and not cls._SAFETY_ASSERTION_PATTERN.search(
            draft_answer
        ):
            return MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION
        draft_dosages = cls._dosage_tokens(draft_answer)
        generated_dosages = cls._dosage_tokens(generated_answer)
        if not generated_dosages.issubset(draft_dosages):
            return MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT
        return None

    @classmethod
    def _dosage_tokens(cls, text: str) -> set[str]:
        """공백을 없앤 뒤 용량을 추출한다.

        추출 후에 공백을 지우면 `4, 000mg`처럼 띄어 쓰인 수치를 정규식이 통째로
        놓쳐 초안과 생성문의 토큰이 어긋난다. 정규화가 먼저 와야 한다.
        """

        return {token.casefold() for token in cls._DOSAGE_TOKEN_PATTERN.findall(re.sub(r"\s+", "", text))}

    @classmethod
    def _omits_interaction_overview(cls, *, draft_answer: str, generated_answer: str) -> bool:
        """근거가 있는 탐색 섹션을 빈 제목·근거 없음 안내로 대체했는지 확인한다."""
        for header in cls._INTERACTION_OVERVIEW_HEADERS:
            draft_section = cls._section_block(answer=draft_answer, header=header)
            if not cls._has_overview_fact_bullet(draft_section):
                continue
            generated_section = cls._section_block(answer=generated_answer, header=header)
            if not cls._has_overview_fact_bullet(generated_section):
                return True
        return False

    @classmethod
    def _has_overview_fact_bullet(cls, section: str | None) -> bool:
        return any(
            line.strip().startswith("- ")
            and line.strip()[2:].strip()
            and not cls._MISSING_EVIDENCE_LINE_PATTERN.search(line)
            for line in (section or "").splitlines()
        )

    @staticmethod
    def _answer_hash(answer: str) -> str:
        return hashlib.sha256(answer.strip().encode("utf-8")).hexdigest()

    @classmethod
    def _restore_required_question_interaction_pairs(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
    ) -> str:
        """LLM이 관계 제목을 생략하면 검증된 초안 섹션을 그대로 보존한다."""

        draft_section = cls._section_block(
            answer=draft_answer,
            header=cls._QUESTION_INTERACTION_HEADER,
        )
        if draft_section is None:
            return generated_answer
        required_pairs = [
            match.group("pair")
            for line in draft_section.splitlines()
            if (match := cls._INTERACTION_PAIR_HEADER_PATTERN.fullmatch(line.strip())) is not None
        ]
        if not required_pairs:
            return generated_answer

        generated_section = cls._section_block(
            answer=generated_answer,
            header=cls._QUESTION_INTERACTION_HEADER,
        )
        if generated_section is not None and all(f"**{pair}**" in generated_section for pair in required_pairs):
            return generated_answer
        if generated_section is None:
            return "\n\n".join(value for value in (generated_answer.strip(), draft_section) if value)
        return generated_answer.replace(generated_section, draft_section)

    @classmethod
    def _restore_required_formulation_cautions(
        cls,
        *,
        draft_answer: str,
        generated_answer: str,
    ) -> str:
        """제형별 공식 주의사항은 LLM이 하나의 일반 안내로 합치지 못하게 한다."""

        draft_section = cls._section_block(
            answer=draft_answer,
            header=cls._CAUTION_SECTION_HEADER,
        )
        if draft_section is None:
            return generated_answer
        required_formulations = [
            match.group("value").strip()
            for line in draft_section.splitlines()
            if (match := cls._STANDALONE_BOLD_LINE_PATTERN.fullmatch(line.strip())) is not None
        ]
        if len(required_formulations) < 2:
            return generated_answer
        generated_section = cls._section_block(
            answer=generated_answer,
            header=cls._CAUTION_SECTION_HEADER,
        )
        if generated_section is not None and all(
            f"**{formulation}**" in generated_section for formulation in required_formulations
        ):
            return generated_answer
        if generated_section is None:
            return "\n\n".join(value for value in (generated_answer.strip(), draft_section) if value)
        return generated_answer.replace(generated_section, draft_section)

    @classmethod
    def _section_block(
        cls,
        *,
        answer: str,
        header: str,
    ) -> str | None:
        lines = answer.splitlines()
        try:
            start = next(index for index, line in enumerate(lines) if line.strip() == header)
        except StopIteration:
            return None
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if cls._SECTION_HEADER_PATTERN.fullmatch(lines[index]) is not None:
                end = index
                break
        return "\n".join(lines[start:end]).strip()

    @classmethod
    def _has_external_rewrite_evidence(cls, result: MedicationChatResult) -> bool:
        """등록 정보는 답변 대상을 식별할 뿐, 의학적 주장의 근거가 되지 않는다."""

        return any(source.kind in cls._LLM_REWRITE_SOURCE_KINDS for source in result.sources)

    @staticmethod
    def _is_evidence_gap_guidance(result: MedicationChatResult) -> bool:
        """근거 부재 안내는 새 의학 주장을 만들지 않는 범위에서만 LLM이 정리한다."""

        return MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value in result.safety_reason_codes

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

        answer = cls._normalize_adverse_report_headers(answer)
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
                subtitle = section_header.group("subtitle") or ""
                normalized_lines.append(f"{icon} **{title}** {subtitle}".rstrip())
                if cls._INTERACTION_SECTION_TITLE in title:
                    interaction_lines = []
                continue
            if standalone_bold_line := cls._STANDALONE_BOLD_LINE_PATTERN.fullmatch(line):
                normalized_lines.append(f"**{standalone_bold_line.group('value').strip()}**")
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

        formatted: list[str] = []
        prose_lines: list[str] = []
        bullet_items: list[list[str]] = []
        current_bullet: list[str] | None = None

        def flush_facts() -> None:
            nonlocal current_bullet
            if current_bullet is not None:
                bullet_items.append(current_bullet)
                current_bullet = None
            facts = cls._interaction_sentences(prose_lines)
            facts.extend(cls._normalize_interaction_fact(item) for item in bullet_items)
            formatted.extend(f"- {fact}" for fact in facts if fact)
            prose_lines.clear()
            bullet_items.clear()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            pair_header = cls._INTERACTION_PAIR_HEADER_PATTERN.fullmatch(line)
            if pair_header is not None:
                flush_facts()
                formatted.append(f"**{pair_header.group('pair')}**")
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

        flush_facts()
        if not formatted:
            return []
        return ["", *formatted]

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
