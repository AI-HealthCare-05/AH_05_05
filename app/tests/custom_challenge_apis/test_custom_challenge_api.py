import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient

from app.core import config
from app.core.config import Config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exceptions import (
    CustomChallengeAlreadyActiveError,
    CustomChallengeIdempotencyConflictError,
    CustomChallengeInvalidTargetsError,
    CustomChallengeParticipationNotFoundError,
    CustomChallengeTemplateUnavailableError,
)
from app.dependencies.security import get_request_user
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.dtos.user_supplement_nutrients import (
    ManualSupplementNutrientCreateRequest,
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.main import app
from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import (
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (
    AccountStatus,
    CareEpisodeStatus,
    CustomChallengeType,
    MealSlot,
    SupplementStatus,
)
from app.models.medications import Medication, MedicationDose, MedicationSlot
from app.models.supplement_nutrients import (
    SupplementDose,
    SupplementNutrient,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import User, UserSettings
from app.repositories.user_supplement_nutrient_repository import UserSupplementNutrientRepository
from app.services.custom_challenges import CustomChallengeService
from app.services.user_supplement_nutrients import UserSupplementNutrientService

NOW = datetime(2026, 9, 8, 7, 30, tzinfo=config.TIMEZONE)
TEST_DATE = NOW.date()


@pytest_asyncio.fixture(autouse=True)
async def initialized_db(monkeypatch: pytest.MonkeyPatch) -> None:
    sqlite3.register_adapter(time, lambda value: value.isoformat())
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    monkeypatch.setattr(config, "CUSTOM_CHALLENGE_TEMPLATE_TYPES", {})
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    await Tortoise.close_connections()


@pytest.fixture
def service() -> CustomChallengeService:
    return CustomChallengeService(now_provider=lambda: NOW)


async def _user(email: str = "custom@example.com") -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name="맞춤 사용자",
        status=AccountStatus.ACTIVE,
    )


async def _templates() -> tuple[CustomChallengeTemplate, CustomChallengeTemplate]:
    group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CUSTOM_API_TEST",
        group_name="맞춤 챌린지 테스트",
    )
    check_type = await CommonCode.create(
        group=group,
        detail_code="AUTO",
        detail_name="자동",
    )
    medication = await CustomChallengeTemplate.create(
        name="7일 복약",
        check_type=check_type,
        is_active=True,
    )
    supplement = await CustomChallengeTemplate.create(
        name="7일 영양제",
        check_type=check_type,
        is_active=True,
    )
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {
        medication.id: CustomChallengeType.MEDICATION,
        supplement.id: CustomChallengeType.SUPPLEMENT,
    }
    return medication, supplement


async def _medication_episode(
    user: User,
    *,
    alias: str = "감기 처방",
    start_date: date = TEST_DATE,
    start_slot: MealSlot = MealSlot.MORNING,
    days: int = 7,
    status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE,
) -> CareEpisode:
    episode = await CareEpisode.create(
        user=user,
        alias=alias,
        status=status,
        medication_start_date=start_date,
        medication_start_slot=start_slot,
        medication_days=days,
    )
    medication = await Medication.create(
        care_episode=episode,
        name="테스트약",
        times_per_day=2,
        days=days,
    )
    await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)
    await MedicationSlot.create(medication=medication, slot=MealSlot.EVENING)
    return episode


async def _supplement(
    user: User,
    *,
    name: str,
    start_date: date = TEST_DATE,
    end_date: date | None = None,
    status: SupplementStatus = SupplementStatus.ACTIVE,
    manual: bool = True,
) -> UserSupplementNutrient:
    product = None
    if not manual:
        product = await SupplementNutrient.create(
            food_code=f"P-{name}",
            name=name,
            basis_qty="1정",
            energy_kcal=0,
            protein_g=Decimal("0"),
            carb_g=Decimal("0"),
            serving_desc="1정",
            serving_size="1정",
            daily_freq="1회",
        )
    registration = await UserSupplementNutrient.create(
        user=user,
        supplement_nutrient=product,
        custom_name=name if manual else None,
        dose_amount=Decimal("1"),
        dose_unit="정",
        start_date=start_date,
        end_date=end_date,
        status=status,
    )
    await UserSupplementNutrientSlot.create(
        user_suppl_nutrient=registration,
        slot=MealSlot.MORNING,
    )
    return registration


def test_config_template_mapping_defaults_and_parses_json() -> None:
    assert Config(_env_file=None).CUSTOM_CHALLENGE_TEMPLATE_TYPES == {}
    parsed = Config(
        _env_file=None,
        CUSTOM_CHALLENGE_TEMPLATE_TYPES='{"41":"MEDICATION","42":"SUPPLEMENT"}',
    )
    assert parsed.CUSTOM_CHALLENGE_TEMPLATE_TYPES == {
        41: CustomChallengeType.MEDICATION,
        42: CustomChallengeType.SUPPLEMENT,
    }


@pytest.mark.parametrize(
    "mapping",
    [
        {0: CustomChallengeType.MEDICATION},
        {41: CustomChallengeType.MEDICATION, 42: CustomChallengeType.MEDICATION},
    ],
)
def test_config_template_mapping_rejects_invalid_entries(mapping: dict[int, CustomChallengeType]) -> None:
    with pytest.raises(ValidationError):
        Config(_env_file=None, CUSTOM_CHALLENGE_TEMPLATE_TYPES=mapping)


def test_join_request_is_canonical_and_strict() -> None:
    request = CustomChallengeJoinRequest(targetIds=[3, 1], idempotencyKey=" request-1 ")
    assert request.target_ids == [1, 3]
    assert request.idempotency_key == "request-1"

    for body in (
        {"targetIds": [], "idempotencyKey": "request-1"},
        {"targetIds": [3, 1, 3], "idempotencyKey": "request-1"},
        {"targetIds": [1], "idempotencyKey": ""},
        {"targetIds": [1], "idempotencyKey": "request-1", "userId": 7},
    ):
        with pytest.raises(ValidationError):
            CustomChallengeJoinRequest.model_validate(body)


async def test_recommendations_are_mapped_eligible_owned_and_read_only(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    other = await _user("other@example.com")
    medication_template, supplement_template = await _templates()
    episode = await _medication_episode(user)
    await _medication_episode(other, alias="타인 처방")
    manual = await _supplement(user, name="수동 비타민")
    standard = await _supplement(user, name="표준 오메가3", manual=False)
    await _supplement(other, name="타인 영양제")
    await _supplement(user, name="완료 영양제", status=SupplementStatus.COMPLETED)

    before = (
        await UserSettings.all().count(),
        await CustomChallengeParticipation.all().count(),
        await CustomChallengeTarget.all().count(),
        await CustomChallengeOccurrence.all().count(),
    )
    response = await service.recommendations(user)
    after = (
        await UserSettings.all().count(),
        await CustomChallengeParticipation.all().count(),
        await CustomChallengeTarget.all().count(),
        await CustomChallengeOccurrence.all().count(),
    )

    assert before == after == (0, 0, 0, 0)
    assert [item.template_id for item in response.items] == [
        medication_template.id,
        supplement_template.id,
    ]
    assert [target.id for target in response.items[0].targets] == [episode.id]
    assert [target.id for target in response.items[1].targets] == [manual.id, standard.id]
    assert response.items[0].action == response.items[1].action == "NONE"


async def test_join_medication_generates_future_goals_and_is_idempotent(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    medication_template, _ = await _templates()
    episode = await _medication_episode(user)
    request = CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="med-request")

    first = await service.join(user, medication_template.id, request)
    retried = await service.join(user, medication_template.id, request)

    assert retried.id == first.id
    assert first.joined_at == NOW
    assert first.end_at == datetime(2026, 9, 15, tzinfo=config.TIMEZONE)
    assert first.target_count == 14
    assert first.completed_count == 0
    assert first.actual_end_date == date(2026, 9, 14)
    assert min(item.scheduled_at for item in first.occurrences) >= NOW
    assert await CustomChallengeParticipation.all().count() == 1


async def test_join_supplement_accepts_many_and_uses_inclusive_source_end(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    _, supplement_template = await _templates()
    first = await _supplement(user, name="비타민", end_date=NOW.date())
    second = await _supplement(user, name="오메가3", end_date=NOW.date() + timedelta(days=1))

    response = await service.join(
        user,
        supplement_template.id,
        CustomChallengeJoinRequest(
            target_ids=[second.id, first.id],
            idempotency_key="supp-request",
        ),
    )

    assert [target.source_id for target in response.targets] == [first.id, second.id]
    assert response.target_count == 3
    assert response.actual_end_date == NOW.date() + timedelta(days=1)


async def test_join_rejects_unmapped_template_and_rolls_back_zero_goal_source(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    medication_template, supplement_template = await _templates()
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES.pop(supplement_template.id)
    with pytest.raises(CustomChallengeTemplateUnavailableError):
        await service.join(
            user,
            supplement_template.id,
            CustomChallengeJoinRequest(target_ids=[1], idempotency_key="unmapped"),
        )

    expired_episode = await _medication_episode(
        user,
        start_date=TEST_DATE - timedelta(days=2),
        days=1,
    )
    with pytest.raises(CustomChallengeInvalidTargetsError):
        await service.join(
            user,
            medication_template.id,
            CustomChallengeJoinRequest(target_ids=[expired_episode.id], idempotency_key="zero-goals"),
        )

    assert await UserSettings.filter(user_id=user.id).count() == 0
    assert await CustomChallengeParticipation.filter(user_id=user.id).count() == 0


async def test_join_rejects_cardinality_ownership_idempotency_and_duplicate_active(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    other = await _user("other@example.com")
    medication_template, supplement_template = await _templates()
    episode = await _medication_episode(user)
    other_episode = await _medication_episode(other)

    with pytest.raises(CustomChallengeInvalidTargetsError):
        await service.join(
            user,
            medication_template.id,
            CustomChallengeJoinRequest(target_ids=[episode.id, other_episode.id], idempotency_key="bad-cardinality"),
        )
    with pytest.raises(CustomChallengeInvalidTargetsError):
        await service.join(
            user,
            medication_template.id,
            CustomChallengeJoinRequest(target_ids=[other_episode.id], idempotency_key="bad-owner"),
        )

    original = CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="same-key")
    await service.join(user, medication_template.id, original)
    with pytest.raises(CustomChallengeIdempotencyConflictError):
        await service.join(
            user,
            supplement_template.id,
            CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="same-key"),
        )
    with pytest.raises(CustomChallengeAlreadyActiveError):
        await service.join(
            user,
            medication_template.id,
            CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="different-key"),
        )


async def test_supplement_duplicate_active_check_uses_exact_canonical_target_set(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    _, supplement_template = await _templates()
    first = await _supplement(user, name="비타민")
    second = await _supplement(user, name="오메가3")
    await service.join(
        user,
        supplement_template.id,
        CustomChallengeJoinRequest(target_ids=[first.id, second.id], idempotency_key="set-1"),
    )

    subset = await service.join(
        user,
        supplement_template.id,
        CustomChallengeJoinRequest(target_ids=[first.id], idempotency_key="set-2"),
    )
    assert [target.source_id for target in subset.targets] == [first.id]

    with pytest.raises(CustomChallengeAlreadyActiveError):
        await service.join(
            user,
            supplement_template.id,
            CustomChallengeJoinRequest(target_ids=[second.id, first.id], idempotency_key="set-3"),
        )


async def test_active_duplicate_is_rejected_after_template_mapping_replacement(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    medication_template, supplement_template = await _templates()
    episode = await _medication_episode(user)
    existing = await service.join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="old-template"),
    )
    replacement = await CustomChallengeTemplate.create(
        name="새 7일 복약",
        check_type_id=medication_template.check_type_id,
        is_active=True,
    )
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {
        replacement.id: CustomChallengeType.MEDICATION,
        supplement_template.id: CustomChallengeType.SUPPLEMENT,
    }

    recommendations = await service.recommendations(user)
    medication_recommendation = next(
        item for item in recommendations.items if item.template_id == replacement.id
    )
    assert medication_recommendation.targets[0].existing_participation_id == existing.id

    with pytest.raises(CustomChallengeAlreadyActiveError):
        await service.join(
            user,
            replacement.id,
            CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="new-template"),
        )

    assert await CustomChallengeParticipation.filter(user_id=user.id).count() == 1


async def test_idempotent_retry_rejects_stored_type_mismatch(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    medication_template, _ = await _templates()
    episode = await _medication_episode(user)
    request = CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="stored-type")
    participation = await service.join(user, medication_template.id, request)
    await CustomChallengeParticipation.filter(id=participation.id).update(
        challenge_type=CustomChallengeType.SUPPLEMENT
    )

    with pytest.raises(CustomChallengeIdempotencyConflictError):
        await service.join(user, medication_template.id, request)


class _LockOrderRepository(UserSupplementNutrientRepository):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def get_user_for_update(
        self,
        user_id: int,
        connection: BaseDBAsyncClient,
    ) -> User | None:
        self.events.append("user")
        return await super().get_user_for_update(user_id, connection)

    async def get_owned_for_update(
        self,
        registration_id: int,
        user_id: int,
        connection: BaseDBAsyncClient,
    ) -> UserSupplementNutrient | None:
        self.events.append("source")
        return await super().get_owned_for_update(registration_id, user_id, connection)

    async def get_by_user_product_for_update(
        self,
        user_id: int,
        product_id: int,
        connection: BaseDBAsyncClient,
    ) -> UserSupplementNutrient | None:
        self.events.append("source")
        return await super().get_by_user_product_for_update(user_id, product_id, connection)

    async def get_or_create_settings(
        self,
        user_id: int,
        connection: BaseDBAsyncClient | None = None,
    ) -> UserSettings:
        if connection is not None:
            self.events.append("settings")
        return await super().get_or_create_settings(user_id, connection)


async def test_supplement_mutations_share_user_source_settings_lock_order() -> None:
    user = await _user()
    repository = _LockOrderRepository()
    service = UserSupplementNutrientService(repository)

    created = await service.create_manual(
        user,
        ManualSupplementNutrientCreateRequest(
            custom_name="수동 영양제",
            dose_amount=Decimal("1"),
            dose_unit="정",
            start_date=TEST_DATE,
            slots=[MealSlot.MORNING],
        ),
    )
    assert repository.events == ["user", "settings"]

    standard = await _supplement(user, name="표준 영양제", manual=False)
    repository.events.clear()
    await service.upsert(
        user,
        standard.supplement_nutrient_id,
        UserSupplementNutrientUpsertRequest(
            dose_amount=Decimal("2"),
            dose_unit="정",
            start_date=TEST_DATE,
            slots=[MealSlot.EVENING],
        ),
    )
    assert repository.events == ["user", "source", "settings"]

    repository.events.clear()
    await service.update(
        user,
        created.id,
        UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH]),
    )
    assert repository.events == ["user", "source", "settings"]

    repository.events.clear()
    await service.complete(user, created.id)
    assert repository.events == ["user", "source", "settings"]


async def test_progress_matches_only_original_scheduled_doses_and_gets_do_not_write(
    service: CustomChallengeService,
) -> None:
    user = await _user()
    medication_template, supplement_template = await _templates()
    episode = await _medication_episode(user)
    registration = await _supplement(user, name="비타민")
    med_joined = await service.join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="med-progress"),
    )
    supplement_joined = await service.join(
        user,
        supplement_template.id,
        CustomChallengeJoinRequest(target_ids=[registration.id], idempotency_key="supp-progress"),
    )
    await MedicationDose.create(
        user=user,
        care_episode=episode,
        dose_date=NOW.date(),
        slot=MealSlot.MORNING,
    )
    unscheduled = await MedicationDose.create(
        user=user,
        care_episode=episode,
        dose_date=NOW.date(),
        slot=MealSlot.LUNCH,
    )
    supplement_dose = await SupplementDose.create(
        registration=registration,
        dose_date=NOW.date(),
        slot=MealSlot.MORNING,
    )

    before = await CustomChallengeOccurrence.all().count()
    listed = await service.list(user)
    med_detail = await service.get(user, med_joined.id)
    supplement_detail = await service.get(user, supplement_joined.id)
    after = await CustomChallengeOccurrence.all().count()

    assert before == after
    assert listed.total_count == 2
    listed_by_id = {item.id: item for item in listed.items}
    assert listed_by_id[med_joined.id].completed_count == med_detail.completed_count
    assert listed_by_id[supplement_joined.id].completed_count == supplement_detail.completed_count
    assert med_detail.completed_count == 1
    assert supplement_detail.completed_count == 1
    assert med_detail.target_count == med_joined.target_count
    await unscheduled.delete()
    await supplement_dose.delete()
    assert (await service.get(user, supplement_joined.id)).completed_count == 0
    assert (await service.get(user, med_joined.id)).completed_count == 1


async def test_detail_hides_other_users_participation(service: CustomChallengeService) -> None:
    user = await _user()
    other = await _user("other@example.com")
    medication_template, _ = await _templates()
    episode = await _medication_episode(user)
    joined = await service.join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="private"),
    )

    with pytest.raises(CustomChallengeParticipationNotFoundError):
        await service.get(other, joined.id)


async def test_routes_require_auth_and_serialize_camel_case(service: CustomChallengeService) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/api/v1/user/custom-challenge-recommendations")
    assert unauthenticated.status_code == 401

    user = await _user()
    medication_template, _ = await _templates()
    episode = await _medication_episode(user)
    app.dependency_overrides[get_request_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        joined = await client.post(
            f"/api/v1/user/custom-challenge-recommendations/{medication_template.id}/participations",
            json={"targetIds": [episode.id], "idempotencyKey": "route-request"},
        )
        listed = await client.get("/api/v1/user/custom-challenge-participations")
        detail = await client.get(
            f"/api/v1/user/custom-challenge-participations/{joined.json()['id']}"
        )

    assert joined.status_code == 201, joined.text
    assert joined.json()["templateId"] == medication_template.id
    assert "targetCount" in joined.json()
    assert listed.json()["items"][0]["targetCount"] == detail.json()["targetCount"]
