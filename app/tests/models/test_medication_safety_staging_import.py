from tortoise.contrib.test import TestCase

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionRiskLevel,
)
from ai_worker.schemas.medication_safety import (
    MedicationSafetyConditionCandidate,
    MedicationSafetyRuleCandidate,
    MedicationSafetyRuleType,
    MedicationSafetySourceRecord,
    SafetyComparisonOperator,
    SafetyConditionKind,
)
from app.models.enums import InteractionReviewStatus
from app.models.interactions import (
    InteractionEntityIdentifier,
    MedicationSafetyRule,
    MedicationSafetyRuleCondition,
    MedicationSafetyRuleSource,
)
from scripts.import_medication_safety_staging import (
    MedicationSafetyStagingDataset,
    import_medication_safety_staging_dataset,
)


def build_candidate() -> MedicationSafetyRuleCandidate:
    return MedicationSafetyRuleCandidate(
        dataset_version="medication-safety-v1",
        entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="아세트아미노펜",
            source_code="D000001",
        ),
        rule_type=MedicationSafetyRuleType.DAILY_MAX_DOSE,
        risk_level=InteractionRiskLevel.HIGH_CAUTION,
        guidance_text="1일 최대 투여량을 넘기지 마세요.",
        conditions=[
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=1,
                condition_kind=SafetyConditionKind.DAILY_DOSE,
                comparison_operator=SafetyComparisonOperator.GT,
                value_min=4000,
                unit="mg/day",
            )
        ],
        sources=[
            MedicationSafetySourceRecord(
                source_id="mfds_drug_records",
                document_id="DUR용량주의.csv",
                record_id="1",
                raw_effect_text="아세트아미노펜 4,000mg",
                source_published_at="2026-01-31",
            )
        ],
    )


class TestMedicationSafetyStagingImporter(TestCase):
    async def test_imports_pending_candidate_and_is_idempotent(self) -> None:
        candidate = build_candidate()
        dataset = MedicationSafetyStagingDataset(
            dataset_version="medication-safety-v1",
            generation_id="a" * 64,
            candidates=[candidate],
            ready_for_rdb_import=False,
            candidate_sha256="b" * 64,
        )

        first = await import_medication_safety_staging_dataset(dataset)
        second = await import_medication_safety_staging_dataset(dataset)

        assert first.rules_created == 1
        assert first.conditions_created == 1
        assert first.sources_created == 1
        assert second.total_created == 0
        rule = await MedicationSafetyRule.get(rule_key=candidate.rule_key)
        assert rule.review_status == InteractionReviewStatus.PENDING
        assert await MedicationSafetyRuleCondition.filter(medication_safety_rule=rule).count() == 1
        assert await MedicationSafetyRuleSource.filter(medication_safety_rule=rule).count() == 1
        assert (
            await InteractionEntityIdentifier.filter(
                source_id="mfds_drug_records",
                source_code="D000001",
            ).count()
            == 1
        )
