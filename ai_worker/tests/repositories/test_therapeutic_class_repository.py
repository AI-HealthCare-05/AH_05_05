from datetime import datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.therapeutic_class_repository import (
    DbTherapeuticClassRepository,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    TherapeuticClassSelectionStatus,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import CareEpisode
from app.models.enums import (
    InteractionEntityKind,
    InteractionMatchMethod,
    InteractionReviewStatus,
)
from app.models.interactions import (
    InteractionEntity,
    InteractionEntityTherapeuticClass,
    MedicationInteractionEntity,
    TherapeuticClass,
    TherapeuticClassAlias,
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
async def test_therapeutic_class_repository_selects_only_approved_classified_active_medications(
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
        title="치료군 테스트",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(2026, 9, 9, 9, 0),
    )
    warfarin = await Medication.create(id=10, care_episode=episode, name="와파린")
    acetaminophen = await Medication.create(id=20, care_episode=episode, name="타이레놀정500밀리그람")
    warfarin_entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    acetaminophen_entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아세트아미노펜",
        normalized_name="아세트아미노펜",
    )
    await MedicationInteractionEntity.create(
        medication=warfarin,
        interaction_entity=warfarin_entity,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text="와파린",
    )
    await MedicationInteractionEntity.create(
        medication=acetaminophen,
        interaction_entity=acetaminophen_entity,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text="타이레놀정500밀리그람",
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
        interaction_entity=warfarin_entity,
        therapeutic_class=anticoagulant,
        review_status=InteractionReviewStatus.APPROVED,
        classification_dataset_version="therapeutic-class-v1",
        source_id="kpicia_pharm_review",
        document_id="kpicia_pharm_review-c4ea8e68b35b65b3",
        record_id="chunk-1",
        raw_classification_text="와파린은 비타민 K 의존성 응혈인자를 저해하여 항응고작용을 한다.",
        approved_at=datetime(2026, 9, 9, 9, 30),
    )

    selection = await DbTherapeuticClassRepository(
        active_dataset_version="therapeutic-class-v1",
    ).select_active_medications(
        context=ActiveIntakeContext(
            user_id=user.id,
            medications=[
                ActiveMedication(
                    medication_id=warfarin.id,
                    care_episode_id=episode.id,
                    name="와파린",
                ),
                ActiveMedication(
                    medication_id=acetaminophen.id,
                    care_episode_id=episode.id,
                    name="타이레놀정500밀리그람",
                ),
            ],
        ),
        question="혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 해?",
    )

    assert selection.status == TherapeuticClassSelectionStatus.MATCHED
    assert selection.class_codes == ["ANTICOAGULANT"]
    assert selection.medication_ids == [warfarin.id]


@pytest.mark.asyncio
async def test_therapeutic_class_repository_rejects_pending_classification(
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
        title="치료군 테스트",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(2026, 9, 9, 9, 0),
    )
    warfarin = await Medication.create(id=10, care_episode=episode, name="와파린")
    warfarin_entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    await MedicationInteractionEntity.create(
        medication=warfarin,
        interaction_entity=warfarin_entity,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text="와파린",
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
        interaction_entity=warfarin_entity,
        therapeutic_class=anticoagulant,
        review_status=InteractionReviewStatus.PENDING,
        classification_dataset_version="therapeutic-class-v1",
        source_id="kpicia_pharm_review",
        document_id="kpicia_pharm_review-c4ea8e68b35b65b3",
        record_id="chunk-1",
        raw_classification_text="와파린은 항응고작용을 한다.",
    )

    selection = await DbTherapeuticClassRepository(
        active_dataset_version="therapeutic-class-v1",
    ).select_active_medications(
        context=ActiveIntakeContext(
            user_id=user.id,
            medications=[
                ActiveMedication(
                    medication_id=warfarin.id,
                    care_episode_id=episode.id,
                    name="와파린",
                )
            ],
        ),
        question="혈액응고와 관련된 약은 무엇인가요?",
    )

    assert selection.status == TherapeuticClassSelectionStatus.NO_APPROVED_ACTIVE_MEDICATION
    assert selection.class_codes == ["ANTICOAGULANT"]
    assert selection.medication_ids == []


@pytest.mark.asyncio
async def test_repository_returns_only_approved_classes_for_named_drug(
    initialized_db: None,
) -> None:
    warfarin = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    anticoagulant = await TherapeuticClass.create(code="ANTICOAGULANT", display_name="항응고제")
    await TherapeuticClassAlias.create(
        therapeutic_class=anticoagulant,
        alias="혈액 응고 억제제",
        normalized_alias="혈액응고억제제",
    )
    await InteractionEntityTherapeuticClass.create(
        interaction_entity=warfarin,
        therapeutic_class=anticoagulant,
        review_status=InteractionReviewStatus.APPROVED,
        classification_dataset_version="therapeutic-class-v1",
        source_id="approved-source",
        document_id="approved-document",
        record_id="approved-record",
        raw_classification_text="와파린의 승인된 치료군 연결",
    )
    pending_class = await TherapeuticClass.create(code="PENDING_CLASS", display_name="미승인계열")
    await InteractionEntityTherapeuticClass.create(
        interaction_entity=warfarin,
        therapeutic_class=pending_class,
        review_status=InteractionReviewStatus.PENDING,
        classification_dataset_version="therapeutic-class-v1",
        source_id="pending-source",
        document_id="pending-document",
        record_id="pending-record",
        raw_classification_text="미승인 연결",
    )

    class_names = await DbTherapeuticClassRepository(
        active_dataset_version="therapeutic-class-v1",
    ).find_approved_class_names(entity_names=["와파린"])

    assert class_names == ["항응고제", "혈액 응고 억제제"]
