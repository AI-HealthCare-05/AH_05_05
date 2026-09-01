from datetime import datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.interaction_rule_repository import (
    DbInteractionRuleRepository,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import CareEpisode
from app.models.enums import (
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionMatchMethod,
    InteractionPairType,
    InteractionReviewStatus,
    InteractionRiskLevel,
)
from app.models.interactions import (
    InteractionEntity,
    InteractionRule,
    InteractionRuleSource,
    MedicationInteractionEntity,
)
from app.models.medications import Medication
from app.models.users import User


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_interaction_repository_returns_only_approved_rules(
    initialized_db: None,
) -> None:
    user = await User.create(
        id=1,
        email="patient@example.com",
        hashed_password="hashed-password",
        name="테스트 사용자",
    )
    episode = await CareEpisode.create(
        id=100,
        user=user,
        title="상호작용 테스트",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(2026, 8, 25, 9, 0),
    )
    aspirin = await Medication.create(id=10, care_episode=episode, name="아스피린")
    warfarin = await Medication.create(id=20, care_episode=episode, name="와파린")
    aspirin_entity = await InteractionEntity.create(
        id=1000,
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아스피린",
        normalized_name="아스피린",
    )
    warfarin_entity = await InteractionEntity.create(
        id=2000,
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    await MedicationInteractionEntity.create(
        medication=aspirin,
        interaction_entity=aspirin_entity,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text="아스피린",
    )
    await MedicationInteractionEntity.create(
        medication=warfarin,
        interaction_entity=warfarin_entity,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text="와파린",
    )
    approved = await InteractionRule.create(
        id=3000,
        pair_key="a" * 64,
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=aspirin_entity,
        right_entity=warfarin_entity,
        risk_level=InteractionRiskLevel.HIGH_CAUTION,
        review_status=InteractionReviewStatus.APPROVED,
        rule_dataset_version="dur-v1",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
        approved_at=datetime(2026, 8, 25, 10, 0),
    )
    pending = await InteractionRule.create(
        id=4000,
        pair_key="b" * 64,
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=aspirin_entity,
        right_entity=warfarin_entity,
        risk_level=InteractionRiskLevel.CAUTION,
        review_status=InteractionReviewStatus.PENDING,
        rule_dataset_version="dur-v2",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
    )
    inactive_approved = await InteractionRule.create(
        id=5000,
        pair_key="c" * 64,
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=aspirin_entity,
        right_entity=warfarin_entity,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        review_status=InteractionReviewStatus.APPROVED,
        rule_dataset_version="dur-v2",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
        approved_at=datetime(2026, 8, 25, 11, 0),
    )
    await InteractionRuleSource.create(
        interaction_rule=approved,
        source_id="MFDS_DUR",
        document_id="dur-ddi",
        record_id="row-1",
        raw_effect_text="출혈 위험이 증가할 수 있어 전문가 확인이 필요합니다.",
        source_url="https://example.org/dur/1",
    )
    await InteractionRuleSource.create(
        interaction_rule=pending,
        source_id="MFDS_DUR",
        document_id="dur-ddi",
        record_id="row-2",
        raw_effect_text="검수 전 규칙입니다.",
    )
    await InteractionRuleSource.create(
        interaction_rule=inactive_approved,
        source_id="MFDS_DUR",
        document_id="dur-ddi",
        record_id="row-3",
        raw_effect_text="활성화되지 않은 이전 또는 다음 버전입니다.",
    )

    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=aspirin.id,
                care_episode_id=episode.id,
                name="아스피린",
            ),
            ActiveMedication(
                medication_id=warfarin.id,
                care_episode_id=episode.id,
                name="와파린",
            ),
        ],
    )

    rules = await DbInteractionRuleRepository(
        active_dataset_version="dur-v1",
    ).find_approved_rules(
        context=context,
    )

    assert [rule.interaction_rule_id for rule in rules] == [approved.id]
    assert rules[0].effect_texts == ["출혈 위험이 증가할 수 있어 전문가 확인이 필요합니다."]


@pytest.mark.asyncio
async def test_interaction_repository_resolves_general_question_entities(
    initialized_db: None,
) -> None:
    ketorolac = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="케토롤락",
        normalized_name="케토롤락",
    )
    aspirin = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아스피린",
        normalized_name="아스피린",
    )
    approved = await InteractionRule.create(
        pair_key="d" * 64,
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=ketorolac,
        right_entity=aspirin,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        review_status=InteractionReviewStatus.APPROVED,
        rule_dataset_version="interaction-pilot-v1",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
        approved_at=datetime(2026, 8, 25, 12, 0),
    )
    await InteractionRuleSource.create(
        interaction_rule=approved,
        source_id="MFDS_DUR",
        document_id="dur-ddi",
        record_id="335",
        raw_effect_text="중증의 위장관계 이상반응 위험",
    )
    context = ActiveIntakeContext(user_id=1)
    repository = DbInteractionRuleRepository(
        active_dataset_version="interaction-pilot-v1",
    )

    rules = await repository.find_approved_rules(
        context=context,
        query_entity_names=["케토롤락", "아스피린"],
    )

    assert [rule.interaction_rule_id for rule in rules] == [approved.id]


@pytest.mark.asyncio
async def test_interaction_repository_rejects_partial_question_entity_match(
    initialized_db: None,
) -> None:
    ketorolac = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="케토롤락",
        normalized_name="케토롤락",
    )
    aspirin = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아스피린",
        normalized_name="아스피린",
    )
    await InteractionRule.create(
        pair_key="e" * 64,
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=ketorolac,
        right_entity=aspirin,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        review_status=InteractionReviewStatus.APPROVED,
        rule_dataset_version="interaction-pilot-v1",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
        approved_at=datetime(2026, 8, 25, 12, 0),
    )
    context = ActiveIntakeContext(user_id=1)

    rules = await DbInteractionRuleRepository(
        active_dataset_version="interaction-pilot-v1",
    ).find_approved_rules(
        context=context,
        query_entity_names=["케토롤락"],
    )

    assert rules == []
