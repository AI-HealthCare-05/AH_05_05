from datetime import datetime, time, timedelta
from importlib import import_module

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dependencies.security import get_request_user
from app.main import app
from app.models.care import CareEpisode
from app.models.challenges import Badge, CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import (
    CustomChallengeBadgeAward,
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import ChallengeParticipationStatus, CustomChallengeType, MealSlot
from app.models.medications import MedicationDose
from app.models.users import User
from app.services.challenges import AdminChallengeService


@pytest_asyncio.fixture(autouse=True)
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    await Tortoise.close_connections()


def _service():
    return import_module("app.services.custom_challenge_badges").CustomChallengeBadgeService()


async def _participation(
    *,
    email: str = "custom-badge@example.com",
    badge_active: bool = True,
    status: ChallengeParticipationStatus = ChallengeParticipationStatus.COMPLETED,
) -> tuple[User, CustomChallengeParticipation, Badge]:
    user = await User.create(email=email, hashed_password="unused", name="맞춤 배지 사용자")
    check_group = await CommonCodeGroup.create(
        category="CHL",
        group_code=f"CST_BADGE_{user.id}",
        group_name="맞춤 배지 테스트",
    )
    check_type = await CommonCode.create(
        group=check_group,
        detail_code="AUTO",
        detail_name="자동",
    )
    badge = await Badge.create(
        name=f"맞춤 배지 {user.id}",
        image_path=f"media/badges/custom-{user.id}.png",
        is_active=badge_active,
    )
    template = await CustomChallengeTemplate.create(
        name=f"맞춤 챌린지 {user.id}",
        check_type=check_type,
        reward_badge=badge,
    )
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name=template.name,
        idempotency_key=f"custom-badge-{user.id}",
        end_at=datetime.now() + timedelta(days=7),
        status=status,
        target_count=1,
        completed_count=1,
        progress_rate=100,
        completed_at=datetime.now() if status == ChallengeParticipationStatus.COMPLETED else None,
        finalized_at=datetime.now() if status == ChallengeParticipationStatus.COMPLETED else None,
    )
    return user, participation, badge


async def test_award_uses_participation_badge_snapshot_and_is_idempotent() -> None:
    _, participation, badge = await _participation()
    replacement = await Badge.create(name="교체 배지", image_path="media/badges/replacement.png")
    template = await CustomChallengeTemplate.get(id=participation.template_id)
    template.reward_badge_id = replacement.id
    await template.save(update_fields=["reward_badge_id"])

    async with in_transaction() as connection:
        first = await _service().award_for_completed_participation(participation, using_db=connection)
        second = await _service().award_for_completed_participation(participation, using_db=connection)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.badge_id == badge.id
    assert first.badge_name == badge.name
    assert first.badge_image_path == badge.image_path
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 1


async def test_retry_preserves_existing_snapshot_after_badge_changes() -> None:
    _, participation, badge = await _participation()
    async with in_transaction() as connection:
        award = await _service().award_for_completed_participation(participation, using_db=connection)
    assert award is not None

    badge.name = "변경된 이름"
    badge.image_path = "media/badges/changed.png"
    badge.is_active = False
    await badge.save()
    async with in_transaction() as connection:
        retried = await _service().award_for_completed_participation(participation, using_db=connection)

    assert retried is not None
    assert retried.id == award.id
    assert retried.badge_name != badge.name
    assert retried.badge_image_path != badge.image_path


async def test_inactive_or_active_participation_is_not_awarded() -> None:
    _, inactive_badge_participation, _ = await _participation(badge_active=False)
    _, active_participation, _ = await _participation(
        email="active-custom-badge@example.com",
        status=ChallengeParticipationStatus.ACTIVE,
    )

    async with in_transaction() as connection:
        inactive_result = await _service().award_for_completed_participation(
            inactive_badge_participation,
            using_db=connection,
        )
        active_result = await _service().award_for_completed_participation(
            active_participation,
            using_db=connection,
        )

    assert inactive_result is None
    assert active_result is None
    assert await CustomChallengeBadgeAward.all().count() == 0


async def test_user_badge_list_is_owned_and_serializes_camel_case() -> None:
    owner, participation, _ = await _participation()
    other, _, _ = await _participation(email="other-custom-badge@example.com")
    async with in_transaction() as connection:
        award = await _service().award_for_completed_participation(participation, using_db=connection)
    assert award is not None

    response = await _service().list_for_user(owner.id)
    payload = response.model_dump(by_alias=True, mode="json")

    assert response.total_count == 1
    assert payload["items"][0] == {
        "id": award.id,
        "participationId": participation.id,
        "badgeId": award.badge_id,
        "badgeName": award.badge_name,
        "badgeImagePath": award.badge_image_path,
        "awardedAt": payload["items"][0]["awardedAt"],
    }
    assert await _service().get_for_participation(other.id, participation.id) is None


async def test_admin_marks_custom_awarded_badge_as_in_use() -> None:
    _, participation, badge = await _participation()
    template = await CustomChallengeTemplate.get(id=participation.template_id)
    template.reward_badge_id = None
    await template.save(update_fields=["reward_badge_id"])
    async with in_transaction() as connection:
        award = await _service().award_for_completed_participation(participation, using_db=connection)
    assert award is not None

    assert await AdminChallengeService._used_badge_ids([badge.id]) == {badge.id}


async def test_custom_badge_api_returns_only_the_authenticated_users_awards() -> None:
    owner, participation, _ = await _participation()
    other, other_participation, _ = await _participation(email="api-other-custom-badge@example.com")
    async with in_transaction() as connection:
        owner_award = await _service().award_for_completed_participation(participation, using_db=connection)
        await _service().award_for_completed_participation(other_participation, using_db=connection)
    assert owner_award is not None
    app.dependency_overrides[get_request_user] = lambda: owner

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/user/custom-challenges/badges")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": owner_award.id,
                "participationId": participation.id,
                "badgeId": owner_award.badge_id,
                "badgeName": owner_award.badge_name,
                "badgeImagePath": owner_award.badge_image_path,
                "awardedAt": response.json()["items"][0]["awardedAt"],
            }
        ],
        "totalCount": 1,
        "availableBadges": [],
    }
    assert other.id != owner.id


async def test_badge_catalog_includes_unearned_intake_badges_without_registered_sources() -> None:
    user = await User.create(email="unearned@example.com", hashed_password="unused", name="미획득")
    type_group = await CommonCodeGroup.create(category="CHL", group_code="CST_CHL_TYPE", group_name="유형")
    check_group = await CommonCodeGroup.create(category="CHL", group_code="CST_CHK_TYPE", group_name="인증")
    check = await CommonCode.create(group=check_group, detail_code="AUTO", detail_name="자동")
    expected = []
    templates = []
    for code, name in [("MEDICATION", "복약"), ("SUPPLEMENT", "영양제"), ("VISIT", "진료")]:
        kind = await CommonCode.create(group=type_group, detail_code=code, detail_name=name)
        badge = await Badge.create(name=f"{name} 배지", image_path=f"media/badges/{code}.png")
        template = await CustomChallengeTemplate.create(
            name=f"{name} 챌린지",
            challenge_type=kind,
            check_type=check,
            reward_badge=badge,
        )
        templates.append(template)
        if code != "VISIT":
            expected.append({"id": badge.id, "name": badge.name, "description": None, "imagePath": badge.image_path})
    await CustomChallengeTemplate.create(
        name="중복 영양제",
        challenge_type_id=templates[1].challenge_type_id,
        check_type=check,
        reward_badge_id=templates[1].reward_badge_id,
    )
    hidden = await Badge.create(name="숨김 배지", image_path="media/hidden.png")
    await CustomChallengeTemplate.create(
        name="비활성 템플릿",
        challenge_type_id=templates[0].challenge_type_id,
        check_type=check,
        reward_badge=hidden,
        is_active=False,
    )
    inactive_badge = await Badge.create(name="비활성 배지", image_path="media/inactive.png", is_active=False)
    await CustomChallengeTemplate.create(
        name="비활성 배지 템플릿",
        challenge_type_id=templates[0].challenge_type_id,
        check_type=check,
        reward_badge=inactive_badge,
    )
    badge_group = await CommonCodeGroup.create(category="CHL", group_code="BDG_TYPE", group_name="배지 유형")
    badge_type = await CommonCode.create(group=badge_group, detail_code="CUSTOM", detail_name="맞춤")
    unlinked = await Badge.create(name="미연결 맞춤 배지", image_path="media/unlinked.png", type=badge_type)
    unlinked_view = {"id": unlinked.id, "name": unlinked.name, "description": None, "imagePath": unlinked.image_path}
    expected.append(unlinked_view)
    app.dependency_overrides[get_request_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/user/custom-challenges/badges")
        assert response.status_code == 200
        assert response.json() == {"items": [], "totalCount": 0, "availableBadges": expected}
        check.is_active = False
        await check.save(update_fields=["is_active"])
        response = await client.get("/api/v1/user/custom-challenges/badges")
        assert response.json() == {"items": [], "totalCount": 0, "availableBadges": [unlinked_view]}
    assert await CustomChallengeParticipation.all().count() == 0
    assert await CustomChallengeBadgeAward.all().count() == 0


@pytest.mark.parametrize("first_entry", ["badge-list", "participation-list", "detail"])
async def test_first_read_finalizes_completed_result_without_awarding(first_entry: str) -> None:
    owner, participation, _ = await _participation(
        email="badge-first-read@example.com",
        status=ChallengeParticipationStatus.ACTIVE,
    )
    now = datetime.now(config.TIMEZONE)
    participation.end_at = now - timedelta(seconds=1)
    await participation.save(update_fields=["end_at"])
    episode = await CareEpisode.create(user=owner, alias="배지 첫 조회 처방")
    target = await CustomChallengeTarget.create(
        participation=participation,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="배지 첫 조회 처방",
    )
    occurrence = await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=now.date(),
        slot=MealSlot.MORNING,
        scheduled_at=datetime.combine(now.date(), time(8), tzinfo=config.TIMEZONE),
    )
    await MedicationDose.create(
        user=owner,
        care_episode=episode,
        dose_date=occurrence.scheduled_date,
        slot=occurrence.slot,
    )
    app.dependency_overrides[get_request_user] = lambda: owner

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        paths = {
            "badge-list": "/api/v1/user/custom-challenges/badges",
            "participation-list": "/api/v1/user/custom-challenge-participations",
            "detail": f"/api/v1/user/custom-challenge-participations/{participation.id}",
        }
        first = await client.get(paths[first_entry])
        assert first.status_code == 200
        response = await client.get("/api/v1/user/custom-challenges/badges")

    assert response.status_code == 200
    assert response.json() == {"items": [], "totalCount": 0, "availableBadges": []}
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 0
    await participation.refresh_from_db()
    assert participation.status is ChallengeParticipationStatus.COMPLETED
    assert participation.finalized_at is not None
    assert (participation.target_count, participation.completed_count, participation.progress_rate) == (1, 1, 100)
    await occurrence.refresh_from_db()
    assert occurrence.is_completed is True

    await MedicationDose.filter(user=owner, care_episode=episode).delete()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        repeated = await client.get(paths[first_entry])
        assert repeated.status_code == 200
    await participation.refresh_from_db()
    await occurrence.refresh_from_db()
    assert participation.status is ChallengeParticipationStatus.COMPLETED
    assert (participation.target_count, participation.completed_count, participation.progress_rate) == (1, 1, 100)
    assert occurrence.is_completed is True
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 0
