from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

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
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRoute,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import GuideSource
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

        response = await self._client.ainvoke(messages)

        if isinstance(
            response,
            ChatAnswerSupplement,
        ):
            supplement = response
        else:
            supplement = ChatAnswerSupplement.model_validate(response)

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
            sources=self._build_sources(
                patient_context=patient_context,
                classification=classification,
                supplement=supplement,
                guideline_chunks=(guideline_chunks),
            ),
        )

    @classmethod
    def _build_sources(
        cls,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        supplement: ChatAnswerSupplement,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> list[GuideSource]:
        source_data: list[dict[str, Any]] = []

        if classification.intent == ChatIntent.LIFESTYLE:
            source_data.extend(cls._build_lifestyle_patient_sources(patient_context))
        if classification.intent == ChatIntent.MEDICATION:
            source_data.extend(cls._build_medication_sources(patient_context))
        if classification.route == ChatRoute.PATIENT_AND_RAG and supplement.public_information:
            source_data.extend(cls._build_public_sources(guideline_chunks))

        return [
            GuideSource.model_validate(
                {
                    **data,
                    "citation_order": (citation_order),
                }
            )
            for citation_order, data in enumerate(
                source_data,
                start=1,
            )
        ]

    @staticmethod
    def _build_medication_sources(
        patient_context: PatientContext,
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_type": (SourceType.PATIENT_SAVED_FIELD),
                "patient_source_kind": (PatientSourceKind.MEDICATION),
                "medication_id": (medication.medication_id),
            }
            for medication in (patient_context.medications)
            if medication.medication_id is not None
        ]

    @staticmethod
    def _build_lifestyle_patient_sources(
        patient_context: PatientContext,
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_type": (SourceType.PATIENT_SAVED_FIELD),
                "patient_source_kind": (PatientSourceKind.CARE_ADVICE),
                "care_advice_id": (instruction.care_advice_id),
            }
            for instruction in (patient_context.instructions)
            if (instruction.care_advice_id is not None)
        ]

    @staticmethod
    def _build_public_sources(
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_type": (SourceType.PUBLIC_RAG_CHUNK),
                "public_dataset_key": (chunk.metadata.dataset_key),
                "dataset_version": (chunk.metadata.dataset_version),
                "vector_chunk_id": (chunk.vector_chunk_id),
                "source_record_key": (chunk.metadata.document_id),
                "source_field": (chunk.metadata.section_title),
                "chunk_type": (chunk.metadata.topic),
                "source_title": (chunk.metadata.title),
                "source_organization": (chunk.metadata.organization),
                "source_url": (chunk.metadata.source_url),
                "source_page_number": (chunk.metadata.page_number),
                "source_license": (chunk.metadata.license),
                "similarity_score": (chunk.similarity_score),
            }
            for chunk in guideline_chunks
        ]
