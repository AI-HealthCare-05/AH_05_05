from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import (
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionReviewStatus,
    InteractionRiskLevel,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)
from app.models.interactions import (
    InteractionEntity,
    MedicationSafetyRule,
    MedicationSafetyRuleCondition,
    MedicationSafetyRuleSource,
)
from scripts.approve_medication_safety_rules import (
    MedicationSafetyApprovalError,
    approve_dataset,
)


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def create_valid_rule(*, dataset_version: str = "medication-safety-v2") -> MedicationSafetyRule:
    entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아세트아미노펜",
        normalized_name="아세트아미노펜",
    )
    rule = await MedicationSafetyRule.create(
        rule_key="a" * 64,
        interaction_entity=entity,
        rule_type=MedicationSafetyRuleType.DOSE_CAUTION,
        risk_level=InteractionRiskLevel.CAUTION,
        guidance_text="1일 최대 용량을 확인하세요.",
        review_status=InteractionReviewStatus.PENDING,
        rule_dataset_version=dataset_version,
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
    )
    await MedicationSafetyRuleCondition.create(
        medication_safety_rule=rule,
        condition_group_no=1,
        condition_order=1,
        condition_kind=SafetyConditionKind.DAILY_DOSE,
        comparison_operator=SafetyComparisonOperator.GTE,
        value_min=Decimal("4000"),
        unit="mg/day",
    )
    await MedicationSafetyRuleSource.create(
        medication_safety_rule=rule,
        source_id="mfds",
        document_id="dur-dose",
        record_id="1",
        raw_effect_text="1일 4000mg 이상 주의",
    )
    return rule


@pytest.mark.asyncio
async def test_dry_run_validates_without_updating_database(initialized_db: None) -> None:
    await create_valid_rule()

    result = await approve_dataset(
        dataset_version="medication-safety-v2",
        reviewer="feature-199-test",
        expected_count=1,
        apply=False,
    )

    rule = await MedicationSafetyRule.get()
    assert result.valid_count == 1
    assert result.newly_approved_count == 0
    assert result.applied is False
    assert rule.review_status == InteractionReviewStatus.PENDING


@pytest.mark.asyncio
async def test_apply_approves_valid_dataset_and_is_idempotent(initialized_db: None) -> None:
    await create_valid_rule()
    approved_at = datetime(2026, 9, 1, 12, 0)

    first = await approve_dataset(
        dataset_version="medication-safety-v2",
        reviewer="feature-199-test",
        expected_count=1,
        apply=True,
        approved_at=approved_at,
    )
    second = await approve_dataset(
        dataset_version="medication-safety-v2",
        reviewer="feature-199-test",
        expected_count=1,
        apply=True,
    )

    rule = await MedicationSafetyRule.get()
    assert first.newly_approved_count == 1
    assert second.newly_approved_count == 0
    assert second.approved_at is not None
    assert second.approved_at.replace(tzinfo=None) == approved_at
    assert rule.review_status == InteractionReviewStatus.APPROVED
    assert rule.approved_at.replace(tzinfo=None) == approved_at


@pytest.mark.asyncio
async def test_count_mismatch_rolls_back_without_approval(initialized_db: None) -> None:
    await create_valid_rule()

    with pytest.raises(MedicationSafetyApprovalError, match="건수"):
        await approve_dataset(
            dataset_version="medication-safety-v2",
            reviewer="feature-199-test",
            expected_count=2,
            apply=True,
        )

    assert (await MedicationSafetyRule.get()).review_status == InteractionReviewStatus.PENDING


@pytest.mark.asyncio
async def test_invalid_rule_rolls_back_entire_dataset(initialized_db: None) -> None:
    rule = await create_valid_rule()
    await MedicationSafetyRuleSource.filter(medication_safety_rule=rule).delete()

    with pytest.raises(MedicationSafetyApprovalError, match="검증"):
        await approve_dataset(
            dataset_version="medication-safety-v2",
            reviewer="feature-199-test",
            expected_count=1,
            apply=True,
        )

    assert (await MedicationSafetyRule.get()).review_status == InteractionReviewStatus.PENDING
