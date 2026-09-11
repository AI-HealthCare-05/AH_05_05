from decimal import Decimal

import pytest

from app.core import config
from app.core.exceptions import CustomChallengeTemplateUnavailableError
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.models.challenges import Badge, CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import CustomChallengeParticipation
from app.models.enums import CustomChallengeType
from app.services.custom_challenges import CustomChallengeService
from app.tests.custom_challenge_apis.test_custom_challenge_api import (
    NOW,
    _medication_episode,
    _supplement,
    _user,
)
from app.tests.custom_challenge_apis.test_custom_challenge_api import (
    initialized_db as initialized_db,
)


@pytest.fixture
def service() -> CustomChallengeService:
    return CustomChallengeService(now_provider=lambda: NOW)


async def _backoffice_template(kind: str, name: str) -> CustomChallengeTemplate:
    check_group, _ = await CommonCodeGroup.get_or_create(
        category="CHL", group_code="CST_CHK_TYPE", defaults={"group_name": "맞춤 인증 방식"}
    )
    check_type, _ = await CommonCode.get_or_create(
        group=check_group, detail_code="AUTO", defaults={"detail_name": "자동"}
    )
    type_group, _ = await CommonCodeGroup.get_or_create(
        category="CHL", group_code="CST_CHL_TYPE", defaults={"group_name": "맞춤 챌린지 유형"}
    )
    challenge_type, _ = await CommonCode.get_or_create(
        group=type_group, detail_code=kind, defaults={"detail_name": kind}
    )
    badge = await Badge.create(name=f"{name} 배지", image_path="media/badges/custom.webp")
    return await CustomChallengeTemplate.create(
        name=name, check_type=check_type, challenge_type=challenge_type, reward_badge=badge
    )


async def test_recommendations_read_backoffice_type_without_id_mapping(service: CustomChallengeService) -> None:
    user = await _user()
    medication = await _backoffice_template("MEDICATION", "복약 챌린지")
    supplement = await _backoffice_template("SUPPLEMENT", "영양제 챌린지")
    episode = await _medication_episode(user)
    registration = await _supplement(user, name="비타민")

    response = await service.recommendations(user)

    assert [(item.template_id, item.challenge_type) for item in response.items] == [
        (medication.id, CustomChallengeType.MEDICATION),
        (supplement.id, CustomChallengeType.SUPPLEMENT),
    ]
    assert response.items[0].targets[0].id == episode.id
    assert response.items[1].targets[0].id == registration.id


async def test_join_and_recommendation_return_configured_reward_badge(service: CustomChallengeService) -> None:
    user = await _user()
    template = await _backoffice_template("MEDICATION", "운영자가 정한 이름")
    episode = await _medication_episode(user)
    # Even stale deployment configuration cannot override the backoffice relation.
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {template.id: CustomChallengeType.SUPPLEMENT}

    recommendation = (await service.recommendations(user)).items[0]
    participation = await service.join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="backoffice")
    )

    assert participation.challenge_type is CustomChallengeType.MEDICATION
    assert participation.challenge_name == "운영자가 정한 이름"
    assert participation.target_count == 14
    assert participation.progress_rate == Decimal("0.00")
    assert recommendation.reward_badge.id == template.reward_badge_id
    assert participation.reward_badge == recommendation.reward_badge
    assert participation.model_dump(by_alias=True)["rewardBadge"]["imagePath"] == "media/badges/custom.webp"


@pytest.mark.parametrize("replacement_type", ["SUPPLEMENT", None])
async def test_identical_retry_preserves_participation_after_backoffice_type_edit(
    service: CustomChallengeService, replacement_type: str | None
) -> None:
    user = await _user()
    template = await _backoffice_template("MEDICATION", "변경 전 복약")
    episode = await _medication_episode(user)
    request = CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="stable-retry")
    original = await service.join(user, template.id, request)
    replacement_id = None
    if replacement_type is not None:
        replacement = await _backoffice_template(replacement_type, "새 유형")
        replacement_id = replacement.challenge_type_id
    await CustomChallengeTemplate.filter(id=template.id).update(challenge_type_id=replacement_id)

    replay = await service.join(user, template.id, request)

    assert replay == original
    assert replay.challenge_type is CustomChallengeType.MEDICATION
    assert await CustomChallengeParticipation.filter(user_id=user.id).count() == 1


@pytest.mark.parametrize(
    "invalid_relation", ["missing_type", "inactive_type", "wrong_group", "inactive_group", "inactive_check"]
)
async def test_invalid_backoffice_relation_is_not_recommended_or_joinable(
    service: CustomChallengeService, invalid_relation: str
) -> None:
    user = await _user()
    template = await _backoffice_template("MEDICATION", "검증 대상")
    episode = await _medication_episode(user)
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {template.id: CustomChallengeType.MEDICATION}
    if invalid_relation == "missing_type":
        await CustomChallengeTemplate.filter(id=template.id).update(challenge_type_id=None)
    elif invalid_relation == "inactive_type":
        await CommonCode.filter(id=template.challenge_type_id).update(is_active=False)
    elif invalid_relation == "wrong_group":
        await CommonCodeGroup.filter(group_code="CST_CHL_TYPE").update(group_code="UNRELATED")
    elif invalid_relation == "inactive_group":
        await CommonCodeGroup.filter(group_code="CST_CHL_TYPE").update(is_active=False)
    else:
        await CommonCode.filter(id=template.check_type_id).update(is_active=False)

    assert (await service.recommendations(user)).items == []
    with pytest.raises(CustomChallengeTemplateUnavailableError):
        await service.join(
            user, template.id, CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="invalid")
        )
