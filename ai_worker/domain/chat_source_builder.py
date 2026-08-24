from typing import Any

from ai_worker.schemas.chat import (
    ChatAnswerSupplement,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    CareEpisodeSourceField,
    ChatIntent,
    ChatRoute,
    PatientSourceKind,
    SourceType,
)
from ai_worker.schemas.guide import GuideSource
from ai_worker.schemas.guideline import RetrievedGuidelineChunk
from ai_worker.schemas.patient import PatientContext


class ChatSourceBuilder:
    """채팅에 실제 표시된 환자·공공 정보의 출처를 만든다."""

    @classmethod
    def build_sources(
        cls,
        *,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        supplement: ChatAnswerSupplement,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> list[GuideSource]:
        source_data = cls._build_patient_source_data(
            patient_context=patient_context,
            intent=classification.intent,
        )
        if classification.route == ChatRoute.PATIENT_AND_RAG and supplement.public_information:
            source_data.extend(cls._build_public_source_data(guideline_chunks))
        return cls._validate_sources(source_data)

    @classmethod
    def build_patient_sources(
        cls,
        *,
        patient_context: PatientContext,
        intent: ChatIntent,
    ) -> list[GuideSource]:
        return cls._validate_sources(
            cls._build_patient_source_data(
                patient_context=patient_context,
                intent=intent,
            )
        )

    @classmethod
    def _build_patient_source_data(
        cls,
        *,
        patient_context: PatientContext,
        intent: ChatIntent,
    ) -> list[dict[str, Any]]:
        if intent == ChatIntent.PATIENT_FACT:
            return cls._build_care_episode_sources(patient_context)
        if intent == ChatIntent.MEDICATION:
            return [
                {
                    "source_type": SourceType.PATIENT_SAVED_FIELD,
                    "patient_source_kind": PatientSourceKind.MEDICATION,
                    "medication_id": medication.medication_id,
                }
                for medication in patient_context.medications
                if medication.medication_id is not None
            ]
        if intent in {
            ChatIntent.LIFESTYLE,
            ChatIntent.WARNING_SIGN,
        }:
            return [
                {
                    "source_type": SourceType.PATIENT_SAVED_FIELD,
                    "patient_source_kind": PatientSourceKind.CARE_ADVICE,
                    "care_advice_id": instruction.care_advice_id,
                }
                for instruction in patient_context.instructions
                if instruction.care_advice_id is not None
            ]
        if intent == ChatIntent.FOLLOW_UP:
            return [
                {
                    "source_type": SourceType.PATIENT_SAVED_FIELD,
                    "patient_source_kind": PatientSourceKind.FOLLOW_UP_VISIT,
                    "follow_up_visit_id": schedule.follow_up_visit_id,
                }
                for schedule in patient_context.follow_up_schedules
                if schedule.follow_up_visit_id is not None
            ]
        return []

    @staticmethod
    def _build_care_episode_sources(
        patient_context: PatientContext,
    ) -> list[dict[str, Any]]:
        fields: list[CareEpisodeSourceField] = []
        if patient_context.diagnoses:
            fields.append(CareEpisodeSourceField.DIAGNOSIS)
        if patient_context.surgery:
            fields.append(CareEpisodeSourceField.SURGERY)
        if patient_context.discharge_date:
            fields.append(CareEpisodeSourceField.DISCHARGE_DATE)
        return [
            {
                "source_type": SourceType.PATIENT_SAVED_FIELD,
                "patient_source_kind": PatientSourceKind.CARE_EPISODE_FIELD,
                "patient_field": field,
            }
            for field in fields
        ]

    @staticmethod
    def _build_public_source_data(
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_type": SourceType.PUBLIC_RAG_CHUNK,
                "public_dataset_key": chunk.metadata.dataset_key,
                "dataset_version": chunk.metadata.dataset_version,
                "vector_chunk_id": chunk.vector_chunk_id,
                "source_record_key": chunk.metadata.document_id,
                "source_field": chunk.metadata.section_title,
                "chunk_type": chunk.metadata.topic,
                "source_title": chunk.metadata.title,
                "source_organization": chunk.metadata.organization,
                "source_url": chunk.metadata.source_url,
                "source_page_number": chunk.metadata.page_number,
                "source_license": chunk.metadata.license,
                "similarity_score": chunk.similarity_score,
            }
            for chunk in guideline_chunks
        ]

    @staticmethod
    def _validate_sources(
        source_data: list[dict[str, Any]],
    ) -> list[GuideSource]:
        return [
            GuideSource.model_validate(
                {
                    **data,
                    "citation_order": citation_order,
                }
            )
            for citation_order, data in enumerate(
                source_data,
                start=1,
            )
        ]
