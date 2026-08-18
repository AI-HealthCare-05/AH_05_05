from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.llm.assemblers.recovery_guide_assembler import (
    RecoveryGuideAssembler,
)
from ai_worker.llm.prompts.recovery_guide_prompt import (
    build_recovery_guide_messages,
)
from ai_worker.schemas.enums import (
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import (
    GuideSource,
    RecoveryGuideContent,
    RecoveryGuideResult,
    RecoveryGuideSupplement,
)
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext


class AsyncGuideClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> RecoveryGuideSupplement | RecoveryGuideContent | dict[str, Any]: ...


class OpenAIRecoveryGuideGenerator:
    def __init__(
        self,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncGuideClient | None = None,
    ) -> None:
        normalized_model = model.strip()

        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")

        self._model_name = normalized_model
        self._assembler = RecoveryGuideAssembler()

        if client is not None:
            self._client = client
            return

        chat_model = ChatOpenAI(
            model=normalized_model,
            temperature=0,
            api_key=api_key,
        )

        self._client = chat_model.with_structured_output(
            RecoveryGuideSupplement,
            method="json_schema",
            strict=True,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> RecoveryGuideResult:
        messages = build_recovery_guide_messages(
            patient_context=patient_context,
            guideline_chunks=guideline_chunks,
        )

        response = await self._client.ainvoke(messages)

        if isinstance(
            response,
            RecoveryGuideSupplement,
        ):
            supplement = response
        elif isinstance(
            response,
            RecoveryGuideContent,
        ):
            supplement = RecoveryGuideSupplement(
                public_information=(response.public_information),
                lifestyle_guide=(response.lifestyle_guide),
            )
        else:
            supplement = RecoveryGuideSupplement.model_validate(response)

        if not guideline_chunks:
            supplement = supplement.model_copy(
                update={
                    "public_information": [],
                },
                deep=True,
            )

        guide_content = self._assembler.assemble(
            patient_context=patient_context,
            supplement=supplement,
        )

        return RecoveryGuideResult(
            care_episode_id=(patient_context.care_episode_id),
            guide_content=guide_content,
            sources=self._build_sources(
                patient_context=patient_context,
                guideline_chunks=guideline_chunks,
            ),
            safety_status=SafetyStatus.PENDING,
        )

    @staticmethod
    def _build_sources(
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> list[GuideSource]:
        sources: list[GuideSource] = []
        patient_source_ids: set[int] = set()

        for medication in patient_context.medications:
            patient_source_ids.update(medication.source_field_ids)

        for instruction in patient_context.instructions:
            if instruction.source_field_id is not None:
                patient_source_ids.add(instruction.source_field_id)

        for schedule in patient_context.follow_up_schedules:
            patient_source_ids.update(schedule.source_field_ids)

        sources.extend(
            GuideSource(
                source_type=(SourceType.PATIENT_SAVED_FIELD),
                extracted_field_id=source_field_id,
            )
            for source_field_id in sorted(patient_source_ids)
        )

        sources.extend(
            GuideSource(
                source_type=(SourceType.PUBLIC_RAG_CHUNK),
                public_dataset_key=(chunk.metadata.dataset_key),
                dataset_version=(chunk.metadata.dataset_version),
                vector_chunk_id=(chunk.vector_chunk_id),
                source_record_key=(chunk.metadata.document_id),
                source_field=(chunk.metadata.section_title),
                chunk_type=chunk.metadata.topic,
                source_title=chunk.metadata.title,
                source_organization=(chunk.metadata.organization),
                source_url=(
                    chunk.metadata.source_url
                ),
                source_page_number=(
                    chunk.metadata.page_number
                ),
                source_license=(
                    chunk.metadata.license
                ),
                similarity_score=(
                    chunk.similarity_score
                ),
            )
            for chunk in guideline_chunks
        )

        return sources
