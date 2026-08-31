from ai_worker.schemas.interaction import normalize_interaction_name
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
)
from app.models.enums import InteractionReviewStatus
from app.models.interactions import (
    InteractionEntity,
    InteractionRule,
    MedicationInteractionEntity,
    SupplementInteractionEntity,
)


class DbInteractionRuleRepository:
    def __init__(self, *, active_dataset_version: str) -> None:
        self._active_dataset_version = active_dataset_version.strip()

    async def find_approved_rules(
        self,
        *,
        context: ActiveIntakeContext,
        query_entity_names: list[str] | None = None,
    ) -> list[InteractionRuleFact]:
        entity_ids = await self._resolve_active_entity_ids(context)
        entity_ids.update(
            await self._resolve_query_entity_ids(query_entity_names or []),
        )
        if len(entity_ids) < 2:
            return []

        rules = await InteractionRule.filter(
            review_status=InteractionReviewStatus.APPROVED,
            rule_dataset_version=self._active_dataset_version,
            left_entity_id__in=entity_ids,
            right_entity_id__in=entity_ids,
        ).prefetch_related(
            "left_entity",
            "right_entity",
            "sources",
            "sources__evidence_chunks",
        )
        ordered_rules = sorted(
            rules,
            key=lambda rule: (
                self._pair_priority(rule.pair_type.value),
                rule.id,
            ),
        )
        return [self._to_fact(rule) for rule in ordered_rules]

    @staticmethod
    async def _resolve_active_entity_ids(
        context: ActiveIntakeContext,
    ) -> set[int]:
        medication_ids = [item.medication_id for item in context.medications]
        supplement_ids = [item.supplement_nutrient_id for item in context.supplements]
        medication_entities = (
            await MedicationInteractionEntity.filter(
                medication_id__in=medication_ids,
            ).values_list("interaction_entity_id", flat=True)
            if medication_ids
            else []
        )
        supplement_entities = (
            await SupplementInteractionEntity.filter(
                supplement_nutrient_id__in=supplement_ids,
            ).values_list("interaction_entity_id", flat=True)
            if supplement_ids
            else []
        )
        return set(medication_entities) | set(supplement_entities)

    @staticmethod
    async def _resolve_query_entity_ids(
        query_entity_names: list[str],
    ) -> set[int]:
        normalized_names = {
            normalize_interaction_name(name).casefold()
            for name in query_entity_names
            if normalize_interaction_name(name)
        }
        if not normalized_names:
            return set()
        return set(
            await InteractionEntity.filter(
                normalized_name__in=normalized_names,
            ).values_list("id", flat=True)
        )

    @staticmethod
    def _pair_priority(pair_type: str) -> int:
        priorities = {
            "DRUG_DRUG": 0,
            "DRUG_SUPPLEMENT": 1,
            "SUPPLEMENT_SUPPLEMENT": 2,
            "DRUG_FOOD": 3,
        }
        return priorities.get(pair_type, 99)

    @staticmethod
    def _to_fact(rule: InteractionRule) -> InteractionRuleFact:
        sources = sorted(rule.sources, key=lambda source: source.id)
        effect_texts = list(dict.fromkeys(source.raw_effect_text for source in sources))
        source_titles = list(dict.fromkeys(source.document_id for source in sources))
        source_urls = list(dict.fromkeys(source.source_url for source in sources if source.source_url))
        evidence_chunk_ids = list(
            dict.fromkeys(chunk.vector_chunk_id for source in sources for chunk in source.evidence_chunks)
        )
        return InteractionRuleFact(
            interaction_rule_id=rule.id,
            pair_key=rule.pair_key,
            pair_type=rule.pair_type.value,
            left_name=rule.left_entity.canonical_name,
            right_name=rule.right_entity.canonical_name,
            risk_level=rule.risk_level.value,
            effect_texts=effect_texts,
            source_titles=source_titles,
            source_urls=source_urls,
            evidence_chunk_ids=evidence_chunk_ids,
        )
