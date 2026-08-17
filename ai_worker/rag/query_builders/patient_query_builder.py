from ai_worker.schemas.guideline import (
    GuidelineSearchQuery,
)
from ai_worker.schemas.patient import PatientContext


class PatientQueryBuilder:
    _TOPIC_LABELS = {
        "MEDICATION": "퇴원 후 복약 주의사항",
        "LIFESTYLE": "퇴원 후 생활관리 및 회복",
        "WARNING_SIGN": "퇴원 후 위험 신호",
        "FOLLOW_UP": "퇴원 후 추적 진료",
    }

    def build(
        self,
        patient_context: PatientContext,
        condition: str,
        topic: str,
        care_phase: str = "POST_DISCHARGE",
        limit: int = 5,
    ) -> GuidelineSearchQuery:
        normalized_condition = (
            self._normalize_required(
                condition,
                field_name="질환 코드",
            )
        )
        normalized_topic = (
            self._normalize_required(
                topic,
                field_name="검색 주제",
            )
        )
        normalized_care_phase = (
            self._normalize_required(
                care_phase,
                field_name="회복 단계",
            )
        )

        query_terms = [
            normalized_condition,
            *patient_context.diagnoses,
        ]

        if normalized_topic == "MEDICATION":
            query_terms.extend(
                medication.drug_name
                for medication
                in patient_context.medications
            )

        query_terms.append(
            self._TOPIC_LABELS.get(
                normalized_topic,
                normalized_topic,
            )
        )

        query = " ".join(
            self._remove_duplicates(
                query_terms
            )
        )

        return GuidelineSearchQuery(
            query=query,
            condition=normalized_condition,
            care_phase=normalized_care_phase,
            topic=normalized_topic,
            limit=limit,
        )

    @staticmethod
    def _normalize_required(
        value: str,
        field_name: str,
    ) -> str:
        normalized = value.strip().upper()

        if not normalized:
            raise ValueError(
                f"{field_name}은 비어 있을 수 없습니다."
            )

        return normalized

    @staticmethod
    def _remove_duplicates(
        values: list[str],
    ) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = value.strip()

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            unique_values.append(normalized)

        return unique_values
