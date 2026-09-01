import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatSourceType,
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
from app.models.users import User


def test_medication_safety_enums_define_supported_rules() -> None:
    assert {item.value for item in MedicationSafetyRuleType} == {
        "PREGNANCY_CONTRAINDICATION",
        "AGE_CONTRAINDICATION",
        "ELDERLY_CAUTION",
        "DOSE_CAUTION",
        "DURATION_CAUTION",
        "DAILY_MAX_DOSE",
        "EXCIPIENT_CAUTION",
    }
    assert SafetyConditionKind.DAILY_DOSE.value == "DAILY_DOSE"
    assert SafetyComparisonOperator.BETWEEN.value == "BETWEEN"
    assert ChatSourceType.MEDICATION_SAFETY_RULE.value == ("MEDICATION_SAFETY_RULE")


async def _create_rule(*, rule_key: str = "a" * 64) -> MedicationSafetyRule:
    entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name=f"테스트 약물 {rule_key[:8]}",
        normalized_name=f"테스트약물{rule_key[:8]}",
    )
    return await MedicationSafetyRule.create(
        rule_key=rule_key,
        interaction_entity=entity,
        rule_type=MedicationSafetyRuleType.AGE_CONTRAINDICATION,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        guidance_text="특정 연령에서는 사용하지 않도록 안내된 성분입니다.",
        review_status=InteractionReviewStatus.PENDING,
        rule_dataset_version="medication-safety-v1",
        extraction_method=(InteractionExtractionMethod.DETERMINISTIC_STRUCTURED),
    )


class TestMedicationSafetyRuleModels(TestCase):
    async def test_keeps_condition_and_source(self) -> None:
        rule = await _create_rule()
        condition = await MedicationSafetyRuleCondition.create(
            medication_safety_rule=rule,
            condition_group_no=1,
            condition_order=1,
            condition_kind=SafetyConditionKind.AGE_YEARS,
            comparison_operator=SafetyComparisonOperator.LT,
            value_min=12,
            unit="year",
        )
        source = await MedicationSafetyRuleSource.create(
            medication_safety_rule=rule,
            source_id="MFDS_DUR_AGE",
            document_id="DUR특정연령대금기.csv",
            record_id="row-1",
            raw_effect_text="12세 미만 투여 금기",
        )

        assert condition.medication_safety_rule_id == rule.id
        assert condition.condition_kind == SafetyConditionKind.AGE_YEARS
        assert source.medication_safety_rule_id == rule.id

    async def test_rejects_duplicate_version_key(self) -> None:
        rule = await _create_rule(rule_key="b" * 64)

        with pytest.raises(IntegrityError):
            await MedicationSafetyRule.create(
                rule_key=rule.rule_key,
                interaction_entity_id=rule.interaction_entity_id,
                rule_type=rule.rule_type,
                risk_level=rule.risk_level,
                guidance_text=rule.guidance_text,
                review_status=rule.review_status,
                rule_dataset_version=rule.rule_dataset_version,
                extraction_method=rule.extraction_method,
            )

    async def test_rejects_duplicate_child_keys(self) -> None:
        rule = await _create_rule(rule_key="c" * 64)
        condition_values = {
            "medication_safety_rule": rule,
            "condition_group_no": 1,
            "condition_order": 1,
            "condition_kind": SafetyConditionKind.AGE_YEARS,
            "comparison_operator": SafetyComparisonOperator.LT,
            "value_min": 12,
            "unit": "year",
        }
        source_values = {
            "medication_safety_rule": rule,
            "source_id": "MFDS_DUR_AGE",
            "document_id": "DUR특정연령대금기.csv",
            "record_id": "row-duplicate",
            "raw_effect_text": "12세 미만 투여 금기",
        }
        await MedicationSafetyRuleCondition.create(**condition_values)
        await MedicationSafetyRuleSource.create(**source_values)

        with pytest.raises(IntegrityError):
            await MedicationSafetyRuleCondition.create(**condition_values)
        with pytest.raises(IntegrityError):
            await MedicationSafetyRuleSource.create(**source_values)

    async def test_chat_source_tracks_safety_rule(self) -> None:
        rule = await _create_rule(rule_key="d" * 64)
        user = await User.create(
            email="medication-safety-source@example.com",
            hashed_password="unused",
            name="안전 규칙 테스트",
        )
        session = await ChatSession.create(user=user)
        message = await ChatMessage.create(
            chat_session=session,
            sequence_no=1,
            role=ChatMessageRole.ASSISTANT,
            content="안전 규칙을 반영한 답변",
        )
        source = await ChatMessageSource.create(
            chat_message=message,
            source_type=ChatSourceType.MEDICATION_SAFETY_RULE,
            medication_safety_rule=rule,
            citation_order=1,
        )

        assert source.medication_safety_rule_id == rule.id
        assert source.source_type == ChatSourceType.MEDICATION_SAFETY_RULE
