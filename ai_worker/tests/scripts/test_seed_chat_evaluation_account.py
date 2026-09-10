from datetime import date, datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)
from ai_worker.repositories.interaction_rule_repository import (
    DbInteractionRuleRepository,
)
from ai_worker.repositories.therapeutic_class_repository import (
    DbTherapeuticClassRepository,
)
from ai_worker.schemas.medication_chat import TherapeuticClassSelectionStatus
from app.core.db.databases import TORTOISE_APP_MODELS
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
    InteractionEntityTherapeuticClass,
    InteractionRule,
    InteractionRuleSource,
    SupplementInteractionEntity,
    TherapeuticClass,
    TherapeuticClassAlias,
)
from app.models.supplement_nutrients import SupplementNutrient, UserSupplementNutrient
from app.models.users import User


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


async def _create_reviewed_prerequisites() -> None:
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
    warfarin = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    vitamin_k = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.SUPPLEMENT,
        canonical_name="비타민 K",
        normalized_name="비타민 k",
    )
    supplement = await SupplementNutrient.create(
        food_code="EVAL-VITAMIN-K",
        name="비타민 K",
        basis_qty="1정",
        energy_kcal=0,
        protein_g="0",
        carb_g="0",
        serving_desc="1정",
        serving_size="1정",
        daily_freq="1회",
    )
    await SupplementInteractionEntity.create(
        supplement_nutrient=supplement,
        interaction_entity=vitamin_k,
        match_method=InteractionMatchMethod.EXACT_NAME,
        source_field="name",
    )
    anticoagulant = await TherapeuticClass.create(
        code="ANTICOAGULANT",
        display_name="항응고제",
    )
    await TherapeuticClassAlias.create(
        therapeutic_class=anticoagulant,
        alias="혈액응고와 관련된 약",
        normalized_alias="혈액응고와 관련된 약",
    )
    await InteractionEntityTherapeuticClass.create(
        interaction_entity=warfarin,
        therapeutic_class=anticoagulant,
        review_status=InteractionReviewStatus.APPROVED,
        classification_dataset_version="therapeutic-class-v1",
        source_id="evaluation-fixture",
        document_id="warfarin-classification",
        record_id="warfarin",
        raw_classification_text="와파린은 항응고제 치료군에 속합니다.",
        approved_at=datetime(2026, 9, 10, 9, 0),
    )
    await _create_approved_rule(
        left=ketorolac,
        right=aspirin,
        pair_type=InteractionPairType.DRUG_DRUG,
        pair_key="ketorolac-aspirin",
    )
    await _create_approved_rule(
        left=warfarin,
        right=vitamin_k,
        pair_type=InteractionPairType.DRUG_SUPPLEMENT,
        pair_key="warfarin-vitamin-k",
    )


async def _create_approved_rule(
    *,
    left: InteractionEntity,
    right: InteractionEntity,
    pair_type: InteractionPairType,
    pair_key: str,
) -> None:
    rule = await InteractionRule.create(
        pair_key=pair_key,
        pair_type=pair_type,
        left_entity=left,
        right_entity=right,
        risk_level=InteractionRiskLevel.HIGH_CAUTION,
        review_status=InteractionReviewStatus.APPROVED,
        rule_dataset_version="interaction-pilot-v1",
        extraction_method=InteractionExtractionMethod.DETERMINISTIC_STRUCTURED,
        approved_at=datetime(2026, 9, 10, 9, 0),
    )
    await InteractionRuleSource.create(
        interaction_rule=rule,
        source_id="evaluation-fixture",
        document_id=f"{pair_key}-source",
        record_id="row-1",
        raw_effect_text="검수된 상호작용 근거입니다.",
    )


@pytest.mark.asyncio
async def test_evaluation_seed_dry_run_checks_approved_prerequisites_without_writing(
    initialized_db: None,
) -> None:
    from scripts.seed_chat_evaluation_account import (
        build_evaluation_seed_plan,
        seed_evaluation_account,
    )

    await _create_reviewed_prerequisites()

    result = await seed_evaluation_account(
        build_evaluation_seed_plan(),
        apply=False,
    )

    assert result.dry_run is True
    assert result.prerequisites.missing == []
    assert result.prerequisites.approved_rule_pair_keys == [
        "ketorolac-aspirin",
        "warfarin-vitamin-k",
    ]
    assert await User.all().count() == 0
    assert await UserSupplementNutrient.all().count() == 0


@pytest.mark.asyncio
async def test_evaluation_seed_is_idempotent_and_supports_active_intake_e2e(
    initialized_db: None,
) -> None:
    from scripts.seed_chat_evaluation_account import (
        build_evaluation_seed_plan,
        seed_evaluation_account,
    )

    await _create_reviewed_prerequisites()
    plan = build_evaluation_seed_plan()

    first = await seed_evaluation_account(
        plan,
        apply=True,
        email="evaluation@example.com",
        password="safe-evaluation-password",
        today=date(2026, 9, 10),
    )
    second = await seed_evaluation_account(
        plan,
        apply=True,
        email="evaluation@example.com",
        password="safe-evaluation-password",
        today=date(2026, 9, 10),
    )

    assert first.dry_run is False
    assert second.user_id == first.user_id
    assert await User.all().count() == 1
    assert await UserSupplementNutrient.all().count() == 1
    assert second.created_medication_count == 0

    context = await DbActiveIntakeContextProvider(
        today_provider=lambda: date(2026, 9, 10),
    ).get_active_context(
        user_id=first.user_id,
        care_episode_id=first.care_episode_id,
    )
    assert [item.name for item in context.medications] == ["케토롤락", "아스피린", "와파린"]
    assert [item.name for item in context.supplements] == ["비타민 K"]

    rules = await DbInteractionRuleRepository(
        active_dataset_version=plan.interaction_rule_dataset_version,
    ).find_approved_rules(context=context)
    assert [rule.pair_key for rule in rules] == ["ketorolac-aspirin", "warfarin-vitamin-k"]
    assert all(rule.effect_texts for rule in rules)

    selection = await DbTherapeuticClassRepository(
        active_dataset_version=plan.therapeutic_class_dataset_version,
    ).select_active_medications(
        context=context,
        question="혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 하나요?",
    )
    assert selection.status == TherapeuticClassSelectionStatus.MATCHED
    assert selection.medication_ids == [
        next(item.medication_id for item in context.medications if item.name == "와파린")
    ]


@pytest.mark.asyncio
async def test_evaluation_seed_rejects_pending_rules_without_creating_user(
    initialized_db: None,
) -> None:
    from scripts.seed_chat_evaluation_account import (
        EvaluationSeedPrerequisiteError,
        build_evaluation_seed_plan,
        seed_evaluation_account,
    )

    await _create_reviewed_prerequisites()
    await InteractionRule.all().update(review_status=InteractionReviewStatus.PENDING)

    with pytest.raises(EvaluationSeedPrerequisiteError, match="승인 상호작용 규칙 없음"):
        await seed_evaluation_account(
            build_evaluation_seed_plan(),
            apply=True,
            email="evaluation@example.com",
            password="safe-evaluation-password",
        )

    assert await User.all().count() == 0
