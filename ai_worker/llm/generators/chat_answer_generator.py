from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.domain.chat_source_builder import ChatSourceBuilder
from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.domain.patient_context_hasher import (
    resolve_patient_context_hash,
)
from ai_worker.llm.assemblers.chat_answer_assembler import (
    ChatAnswerAssembler,
)
from ai_worker.llm.prompts.chat_answer_prompt import (
    CHAT_ANSWER_PROMPT_VERSION,
    build_chat_answer_messages,
)
from ai_worker.schemas.chat import (
    CHAT_ANSWER_SCHEMA_VERSION,
    ChatAnswerRequest,
    ChatAnswerResult,
    ChatAnswerSupplement,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext


class AsyncChatAnswerClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> ChatAnswerSupplement | dict[str, Any]: ...


class OpenAIChatAnswerGenerator:
    def __init__(
        self,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncChatAnswerClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        normalized_model = model.strip()

        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")

        self._model_name = normalized_model
        self._assembler = ChatAnswerAssembler()

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
            ChatAnswerSupplement,
            method="json_schema",
            strict=True,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        messages = build_chat_answer_messages(
            request=request,
            patient_context=patient_context,
            classification=classification,
            guideline_chunks=guideline_chunks,
        )

        try:
            response = await self._client.ainvoke(messages)

            if isinstance(
                response,
                ChatAnswerSupplement,
            ):
                supplement = response
            else:
                supplement = ChatAnswerSupplement.model_validate(response)
        except Exception as error:
            raise ChatAnswerGenerationError("챗봇 답변 생성에 실패했습니다.") from error

        if not guideline_chunks:
            supplement = supplement.model_copy(
                update={
                    "public_information": [],
                },
                deep=True,
            )

        answer = self._assembler.assemble(
            patient_context=patient_context,
            classification=classification,
            supplement=supplement,
        )

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=(patient_context.care_episode_id),
            answer=answer,
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash=(resolve_patient_context_hash(patient_context)),
            model_name=self._model_name,
            model_version=None,
            prompt_version=(CHAT_ANSWER_PROMPT_VERSION),
            schema_version=(CHAT_ANSWER_SCHEMA_VERSION),
            sources=ChatSourceBuilder.build_sources(
                patient_context=patient_context,
                classification=classification,
                supplement=supplement,
                guideline_chunks=(guideline_chunks),
            ),
        )
