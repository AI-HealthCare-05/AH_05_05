from datetime import timedelta
from importlib import import_module

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.security import get_request_user
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.main import app
from app.models.challenges import Badge
from app.models.custom_challenges import CustomChallengeBadgeAward, CustomChallengeParticipation
from app.models.enums import ChallengeParticipationStatus, CustomChallengeType
from app.models.medications import MedicationDose
from app.models.supplement_nutrients import SupplementDose
from app.services.custom_challenge_lifecycle import CustomChallengeLifecycleService
from app.services.custom_challenges import CustomChallengeService
from app.tests.custom_challenge_apis.test_custom_challenge_api import (
    NOW,
    _medication_episode,
    _supplement,
    _templates,
    _user,
)
from app.tests.custom_challenge_apis.test_custom_challenge_api import initialized_db as initialized_db


async def _joined(challenge_type: CustomChallengeType):
    user = await _user()
    medication, supplement = await _templates()
    template = medication if challenge_type is CustomChallengeType.MEDICATION else supplement
    badge = await Badge.create(name="취소하면 지급하지 않는 배지", image_path="cancel.png")
    template.reward_badge = badge
    await template.save(update_fields=["reward_badge_id"])
    source = (
        await _medication_episode(user)
        if challenge_type is CustomChallengeType.MEDICATION
        else await _supplement(user, name="비타민")
    )
    service = CustomChallengeService(now_provider=lambda: NOW)
    participation = await service.join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[source.id], idempotency_key="before-cancel")
    )
    return user, source, service, participation


async def _dose(user, source, occurrence, challenge_type):
    if challenge_type is CustomChallengeType.MEDICATION:
        return await MedicationDose.create(
            user=user, care_episode=source, dose_date=occurrence.scheduled_date, slot=occurrence.slot
        )
    return await SupplementDose.create(registration=source, dose_date=occurrence.scheduled_date, slot=occurrence.slot)


async def _cancel(user, participation_id, service, monkeypatch):
    app.dependency_overrides[get_request_user] = lambda: user
    monkeypatch.setattr(import_module("app.apis.v1.challenge_router"), "CustomChallengeService", lambda: service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(f"/api/v1/user/custom-challenge-participations/{participation_id}/cancel")


@pytest.mark.parametrize("challenge_type", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
async def test_cancel_freezes_progress_retains_doses_and_allows_fresh_join(challenge_type, monkeypatch):
    user, source, service, participation = await _joined(challenge_type)
    dose = await _dose(user, source, participation.occurrences[0], challenge_type)

    response = await _cancel(user, participation.id, service, monkeypatch)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "CANCELLED"
    assert result["completedCount"] == 1
    assert result["targetCount"] == (14 if challenge_type is CustomChallengeType.MEDICATION else 7)
    assert [row["isCompleted"] for row in result["occurrences"]] == [True] + [False] * (result["targetCount"] - 1)
    assert await type(dose).filter(id=dose.id).exists()
    stored = await CustomChallengeParticipation.get(id=participation.id)
    assert stored.finalized_at == NOW
    assert stored.completed_at is None
    assert await CustomChallengeBadgeAward.all().count() == 0

    await dose.delete()
    await _dose(user, source, participation.occurrences[1], challenge_type)
    later_service = CustomChallengeService(now_provider=lambda: NOW + timedelta(days=10))
    repeated = await _cancel(user, participation.id, later_service, monkeypatch)
    assert repeated.status_code == 200
    assert repeated.json() == result
    assert (await CustomChallengeParticipation.get(id=participation.id)).finalized_at == NOW
    assert (await later_service.get(user, participation.id)).model_dump(by_alias=True, mode="json") == result
    assert await CustomChallengeLifecycleService().finalize_due(NOW + timedelta(days=10)) == 0

    recommendations = await service.recommendations(user)
    target = next(
        target
        for recommendation in recommendations.items
        if recommendation.challenge_type is challenge_type
        for target in recommendation.targets
        if target.id == source.id
    )
    assert target.existing_participation_id is None
    rejoined = await service.join(
        user,
        participation.template_id,
        CustomChallengeJoinRequest(target_ids=[source.id], idempotency_key="after-cancel"),
    )
    assert rejoined.id != participation.id
    assert rejoined.status is ChallengeParticipationStatus.ACTIVE
    assert (await service.get(user, participation.id)).status is ChallengeParticipationStatus.CANCELLED


async def test_cancel_at_full_progress_before_end_does_not_award(monkeypatch):
    user, source, service, participation = await _joined(CustomChallengeType.SUPPLEMENT)
    for occurrence in participation.occurrences:
        await _dose(user, source, occurrence, CustomChallengeType.SUPPLEMENT)
    response = await _cancel(user, participation.id, service, monkeypatch)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["completedCount"] == 7
    assert response.json()["progressRate"] == "100.00"
    assert await CustomChallengeBadgeAward.all().count() == 0


@pytest.mark.parametrize("completed", [True, False])
async def test_cancel_at_end_commits_final_result_before_conflict_and_preserves_it(completed, monkeypatch):
    user, source, _service, participation = await _joined(CustomChallengeType.MEDICATION)
    if completed:
        for occurrence in participation.occurrences:
            await _dose(user, source, occurrence, CustomChallengeType.MEDICATION)
    service = CustomChallengeService(now_provider=lambda: participation.end_at)

    response = await _cancel(user, participation.id, service, monkeypatch)

    assert response.status_code == 409
    assert response.json()["code"] == "CUSTOM_CHALLENGE_CANCEL_NOT_ALLOWED"
    stored = await CustomChallengeParticipation.get(id=participation.id)
    assert stored.status is (
        ChallengeParticipationStatus.COMPLETED if completed else ChallengeParticipationStatus.EXPIRED
    )
    assert stored.finalized_at == participation.end_at
    assert stored.completed_count == (14 if completed else 0)
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 0
    frozen = (await service.get(user, participation.id)).model_dump()
    await MedicationDose.filter(user_id=user.id).delete()
    repeated = await _cancel(user, participation.id, service, monkeypatch)
    assert repeated.status_code == 409
    assert (await service.get(user, participation.id)).model_dump() == frozen
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 0


async def test_cancel_cannot_access_another_users_participation_or_missing_id(monkeypatch):
    user, _source, service, participation = await _joined(CustomChallengeType.MEDICATION)
    other = await _user("other-cancel@example.com")
    for participation_id in (participation.id, participation.id + 100):
        response = await _cancel(other, participation_id, service, monkeypatch)
        assert response.status_code == 404
        assert response.json()["code"] == "CUSTOM_CHALLENGE_PARTICIPATION_NOT_FOUND"
    stored = await CustomChallengeParticipation.get(id=participation.id)
    assert stored.user_id == user.id
    assert stored.status is ChallengeParticipationStatus.ACTIVE
    assert stored.finalized_at is None
