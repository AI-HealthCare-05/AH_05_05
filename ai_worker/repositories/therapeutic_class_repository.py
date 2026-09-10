from collections import defaultdict

from ai_worker.schemas.interaction import (
    InteractionEntityKind,
    normalize_interaction_name,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    TherapeuticClassSelection,
    TherapeuticClassSelectionStatus,
)
from app.models.enums import InteractionReviewStatus
from app.models.interactions import (
    InteractionEntity,
    InteractionEntityAlias,
    InteractionEntityTherapeuticClass,
    MedicationInteractionEntity,
    TherapeuticClassAlias,
)


class DbTherapeuticClassRepository:
    """검수된 치료군 표현으로 활성 복약정보를 안전하게 좁힌다."""

    def __init__(self, *, active_dataset_version: str) -> None:
        self._active_dataset_version = active_dataset_version.strip()

    async def select_active_medications(
        self,
        *,
        context: ActiveIntakeContext,
        question: str,
    ) -> TherapeuticClassSelection:
        matched_classes = await self._find_matching_classes(question)
        if not matched_classes:
            return TherapeuticClassSelection(
                status=TherapeuticClassSelectionStatus.NOT_REQUESTED,
            )

        class_ids = {item["therapeutic_class_id"] for item in matched_classes}
        class_codes = list(dict.fromkeys(item["therapeutic_class__code"] for item in matched_classes))
        entity_ids_by_medication_id = await self._resolve_active_medication_entity_ids(context)
        if not entity_ids_by_medication_id:
            return TherapeuticClassSelection(
                status=TherapeuticClassSelectionStatus.NO_APPROVED_ACTIVE_MEDICATION,
                class_codes=class_codes,
            )

        approved_classifications = await InteractionEntityTherapeuticClass.filter(
            interaction_entity_id__in={
                entity_id for entity_ids in entity_ids_by_medication_id.values() for entity_id in entity_ids
            },
            therapeutic_class_id__in=class_ids,
            review_status=InteractionReviewStatus.APPROVED,
            classification_dataset_version=self._active_dataset_version,
        ).values_list("interaction_entity_id", flat=True)
        approved_entity_ids = set(approved_classifications)
        medication_ids = [
            medication.medication_id
            for medication in context.medications
            if entity_ids_by_medication_id.get(medication.medication_id, set()).intersection(approved_entity_ids)
        ]
        if not medication_ids:
            return TherapeuticClassSelection(
                status=TherapeuticClassSelectionStatus.NO_APPROVED_ACTIVE_MEDICATION,
                class_codes=class_codes,
            )
        return TherapeuticClassSelection(
            status=TherapeuticClassSelectionStatus.MATCHED,
            class_codes=class_codes,
            medication_ids=medication_ids,
        )

    @staticmethod
    async def _find_matching_classes(question: str) -> list[dict[str, int | str]]:
        normalized_question = _compact_name(question)
        if not normalized_question:
            return []
        aliases = await TherapeuticClassAlias.all().values(
            "therapeutic_class_id",
            "normalized_alias",
            "therapeutic_class__code",
        )
        matched = [
            alias
            for alias in aliases
            if (normalized_alias := _compact_name(str(alias["normalized_alias"])))
            and normalized_alias in normalized_question
        ]
        return sorted(
            matched, key=lambda item: (str(item["therapeutic_class__code"]), int(item["therapeutic_class_id"]))
        )

    @staticmethod
    async def _resolve_active_medication_entity_ids(
        context: ActiveIntakeContext,
    ) -> dict[int, set[int]]:
        medication_ids = [medication.medication_id for medication in context.medications]
        if not medication_ids:
            return {}
        entity_ids_by_medication_id: dict[int, set[int]] = defaultdict(set)
        mapped_rows = await MedicationInteractionEntity.filter(
            medication_id__in=medication_ids,
        ).values_list("medication_id", "interaction_entity_id")
        for medication_id, entity_id in mapped_rows:
            entity_ids_by_medication_id[medication_id].add(entity_id)

        normalized_names_by_medication_id = {
            medication.medication_id: normalize_interaction_name(medication.name).casefold()
            for medication in context.medications
        }
        normalized_names = set(normalized_names_by_medication_id.values())
        if not normalized_names:
            return dict(entity_ids_by_medication_id)
        entity_rows = await InteractionEntity.filter(
            entity_kind=InteractionEntityKind.DRUG,
            normalized_name__in=normalized_names,
        ).values_list("id", "normalized_name")
        alias_rows = await InteractionEntityAlias.filter(
            interaction_entity__entity_kind=InteractionEntityKind.DRUG,
            normalized_alias__in=normalized_names,
        ).values_list("interaction_entity_id", "normalized_alias")
        entity_ids_by_name: dict[str, set[int]] = defaultdict(set)
        for entity_id, normalized_name in [*entity_rows, *alias_rows]:
            entity_ids_by_name[normalized_name].add(entity_id)
        for medication_id, normalized_name in normalized_names_by_medication_id.items():
            entity_ids_by_medication_id[medication_id].update(entity_ids_by_name[normalized_name])
        return dict(entity_ids_by_medication_id)


def _compact_name(value: str) -> str:
    return "".join(normalize_interaction_name(value).casefold().split())
