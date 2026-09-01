import pytest
from pydantic import ValidationError

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionReviewStatus,
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


def build_candidate(
    *,
    sources: list[MedicationSafetySourceRecord] | None = None,
) -> MedicationSafetyRuleCandidate:
    return MedicationSafetyRuleCandidate(
        dataset_version=" medication-safety-2026-09 ",
        entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name=" 아세트아미노펜 ",
            source_code="D000001",
        ),
        rule_type=MedicationSafetyRuleType.DAILY_MAX_DOSE,
        risk_level=InteractionRiskLevel.HIGH_CAUTION,
        guidance_text=" 1일 최대 투여량을 넘기지 마세요. ",
        conditions=[
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=2,
                condition_kind=SafetyConditionKind.ADMINISTRATION_ROUTE,
                comparison_operator=SafetyComparisonOperator.EQ,
                value_text=" 경구 ",
            ),
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=1,
                condition_kind=SafetyConditionKind.DAILY_DOSE,
                comparison_operator=SafetyComparisonOperator.GT,
                value_min="4000",
                unit=" mg/day ",
            ),
        ],
        sources=sources
        or [
            MedicationSafetySourceRecord(
                source_id=" mfds_drug_records ",
                document_id=" 1일최대투여량.csv ",
                record_id=" row-1 ",
                raw_effect_text=" 1일 최대 투여량 4000mg ",
            )
        ],
    )


def test_candidate_normalizes_and_builds_stable_rule_key() -> None:
    first = build_candidate()
    second = build_candidate()

    assert first.dataset_version == "medication-safety-2026-09"
    assert first.guidance_text == "1일 최대 투여량을 넘기지 마세요."
    assert [item.condition_order for item in first.conditions] == [1, 2]
    assert first.conditions[0].unit == "mg/day"
    assert first.review_status == InteractionReviewStatus.PENDING
    assert len(first.rule_key) == 64
    assert first.rule_key == second.rule_key


def test_candidate_rule_key_does_not_depend_on_source_order() -> None:
    first_source = MedicationSafetySourceRecord(
        source_id="mfds",
        document_id="daily.csv",
        record_id="1",
        raw_effect_text="첫 번째 원문",
    )
    second_source = MedicationSafetySourceRecord(
        source_id="mfds",
        document_id="daily.csv",
        record_id="2",
        raw_effect_text="두 번째 원문",
    )

    first = build_candidate(sources=[first_source, second_source])
    second = build_candidate(sources=[second_source, first_source])

    assert first.rule_key == second.rule_key
    assert [item.record_id for item in first.sources] == ["1", "2"]


def test_candidate_rejects_non_pending_review_status() -> None:
    values = build_candidate().model_dump()
    values["review_status"] = InteractionReviewStatus.APPROVED

    with pytest.raises(ValidationError, match="PENDING"):
        MedicationSafetyRuleCandidate.model_validate(values)


def test_between_condition_requires_ordered_bounds() -> None:
    with pytest.raises(ValidationError, match="value_min"):
        MedicationSafetyConditionCandidate(
            condition_group_no=1,
            condition_order=1,
            condition_kind=SafetyConditionKind.AGE_YEARS,
            comparison_operator=SafetyComparisonOperator.BETWEEN,
            value_min=18,
        )
