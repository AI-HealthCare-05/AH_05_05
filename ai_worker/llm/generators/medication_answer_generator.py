import hashlib
import re
from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.llm.prompts.medication_chat_prompt import (
    MEDICATION_CHAT_PROMPT_VERSION,
    build_medication_chat_messages,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationAnswerFallbackReason,
    MedicationAnswerGenerationObservation,
    MedicationAnswerGenerationOutcome,
    MedicationAnswerRewriteStatus,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)


class MedicationAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)


class AsyncMedicationAnswerClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> MedicationAnswerPayload | dict[str, Any]: ...


class OpenAIMedicationAnswerGenerator:
    _DOSAGE_TOKEN_PATTERN = re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|μg|㎍|g|mL|ml|정|캡슐|포|회|일|시간|%)",
        re.IGNORECASE,
    )
    _SAFETY_ASSERTION_PATTERN = re.compile(
        r"(?:안전|문제\s*없|괜찮)[^.!?。！？]{0,12}(?:합니다|해요|습니다)|"
        r"(?:상호작용|부작용)(?:이|은|는)?\s*없(?:습니다|어요)",
        re.IGNORECASE,
    )

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
        if client is not None:
            self._client = client
            return
        chat_model = ChatOpenAI(
            model=normalized_model,
            temperature=0,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._client = chat_model.with_structured_output(
            MedicationAnswerPayload,
            method="json_schema",
            strict=True,
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
        if not result.sources:
            return self._skipped_outcome(
                result,
                draft_hash=draft_hash,
                reason=MedicationAnswerFallbackReason.NO_GROUNDED_SOURCES,
            )
        messages = build_medication_chat_messages(
            request=request,
            context=context,
            result=result,
        )
        try:
            response = await self._client.ainvoke(messages)
            payload = (
                response
                if isinstance(response, MedicationAnswerPayload)
                else MedicationAnswerPayload.model_validate(response)
            )
        except Exception as error:
            raise ChatAnswerGenerationError(
                "약·영양제 챗봇 답변 생성에 실패했습니다.",
                reason_code=MedicationAnswerFallbackReason.CLIENT_ERROR.value,
            ) from error
        generated_answer = self._to_plain_text(payload.answer)
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

    @staticmethod
    def _to_plain_text(answer: str) -> str:
        lines = [re.sub(r"^\s{0,3}#{1,6}\s*", "", line) for line in answer.splitlines()]
        plain_text = "\n".join(lines)
        plain_text = re.sub(r"\*\*(.+?)\*\*", r"\1", plain_text)
        plain_text = re.sub(r"__(.+?)__", r"\1", plain_text)
        return plain_text.strip()
