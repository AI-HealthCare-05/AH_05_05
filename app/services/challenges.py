from datetime import datetime

from tortoise.exceptions import IntegrityError

from app.core import config
from app.core.exceptions import (
    BadgeInUseError,
    BadgeNameAlreadyExistsError,
    BadgeNotFoundError,
    ChallengeInUseError,
    ChallengeNotFoundError,
    CustomChallengeTemplateNameAlreadyExistsError,
    CustomChallengeTemplateNotFoundError,
    InvalidCommonCodeError,
)
from app.dtos.challenges import (
    BadgeAdminListQuery,
    BadgeCreateRequest,
    BadgeResponse,
    BadgeUpdateRequest,
    ChallengeAdminListQuery,
    ChallengeCreateRequest,
    ChallengeResponse,
    ChallengeUpdateRequest,
    CustomChallengeTemplateAdminListQuery,
    CustomChallengeTemplateCreateRequest,
    CustomChallengeTemplateResponse,
    CustomChallengeTemplateUpdateRequest,
)
from app.models.challenges import Badge, Challenge, CustomChallengeTemplate, UserBadge, UserChallenge
from app.models.common_codes import CommonCode
from app.models.custom_challenges import CustomChallengeBadgeAward, CustomChallengeParticipation
from app.repositories.badge_repository import BadgeRepository
from app.repositories.challenge_repository import ChallengeRepository
from app.repositories.custom_challenge_template_repository import CustomChallengeTemplateRepository

_COMMON_CODE_GROUPS = {
    "challenge_type_id": "CHL_TYPE",
    "challenge_period_id": "CHL_PERIOD",
    "check_type_id": "CHK_TYPE",
    "check_frequency_id": "CHK_FREQ",
}


class AdminChallengeService:
    def __init__(self) -> None:
        self.badges = BadgeRepository()
        self.challenges = ChallengeRepository()
        self.custom_templates = CustomChallengeTemplateRepository()

    async def create_badge(self, data: BadgeCreateRequest, admin_id: int) -> BadgeResponse:
        values = data.model_dump()
        badge_type = values.pop("type")
        if badge_type is not None:
            await self._validate_common_code(badge_type, "BDG_TYPE")
        values["type_id"] = badge_type
        try:
            badge = await Badge.create(**values, created_by_admin_id=admin_id)
        except IntegrityError as error:
            raise BadgeNameAlreadyExistsError() from error
        return self.badge_response(badge)

    async def list_badges(self, query: BadgeAdminListQuery) -> tuple[list[BadgeResponse], int]:
        items, total = await self.badges.list(**query.model_dump())
        used_badge_ids = await self._used_badge_ids([item.id for item in items])
        return [self.badge_response(item, is_deletable=item.id not in used_badge_ids) for item in items], total

    async def get_badge(self, badge_id: int) -> BadgeResponse:
        badge = await self.badges.get(badge_id)
        if badge is None:
            raise BadgeNotFoundError()
        return self.badge_response(badge)

    async def update_badge(
        self,
        badge_id: int,
        data: BadgeUpdateRequest,
        admin_id: int,
    ) -> BadgeResponse:
        badge = await self.badges.get(badge_id)
        if badge is None:
            raise BadgeNotFoundError()
        values = data.model_dump(exclude_unset=True)
        if "type" in values:
            badge_type = values.pop("type")
            if badge_type is not None:
                await self._validate_common_code(badge_type, "BDG_TYPE")
            values["type_id"] = badge_type
        for key, value in values.items():
            setattr(badge, key, value)
        badge.updated_by_admin_id = admin_id
        try:
            await badge.save()
        except IntegrityError as error:
            raise BadgeNameAlreadyExistsError() from error
        return self.badge_response(badge)

    async def delete_badge(self, badge_id: int) -> None:
        badge = await self.badges.get(badge_id)
        if badge is None:
            raise BadgeNotFoundError()
        if badge_id in await self._used_badge_ids([badge_id]):
            raise BadgeInUseError()
        try:
            await badge.delete()
        except IntegrityError as error:
            raise BadgeInUseError() from error

    @staticmethod
    async def _used_badge_ids(badge_ids: list[int]) -> set[int]:
        if not badge_ids:
            return set()
        challenge_ids = await Challenge.filter(reward_badge_id__in=badge_ids).values_list(
            "reward_badge_id",
            flat=True,
        )
        template_ids = await CustomChallengeTemplate.filter(
            reward_badge_id__in=badge_ids,
        ).values_list("reward_badge_id", flat=True)
        awarded_ids = await UserBadge.filter(badge_id__in=badge_ids).values_list(
            "badge_id",
            flat=True,
        )
        custom_awarded_ids = await CustomChallengeBadgeAward.filter(
            badge_id__in=badge_ids,
        ).values_list("badge_id", flat=True)
        custom_snapshot_ids = await CustomChallengeParticipation.filter(
            reward_badge_id__in=badge_ids,
        ).values_list("reward_badge_id", flat=True)
        return (
            set(challenge_ids)
            | set(template_ids)
            | set(awarded_ids)
            | set(custom_awarded_ids)
            | set(custom_snapshot_ids)
        )

    async def create_challenge(
        self,
        data: ChallengeCreateRequest,
        admin_id: int,
    ) -> ChallengeResponse:
        await self._validate_challenge_relations(data.model_dump())
        challenge = await Challenge.create(**data.model_dump(), created_by_admin_id=admin_id)
        return self.challenge_response(challenge)

    async def list_challenges(
        self,
        query: ChallengeAdminListQuery,
    ) -> tuple[list[ChallengeResponse], int]:
        items, total = await self.challenges.list(**query.model_dump())
        challenge_ids = [item.id for item in items]
        joined_ids = set(
            await UserChallenge.filter(challenge_id__in=challenge_ids).values_list(
                "challenge_id",
                flat=True,
            )
        )
        return [self.challenge_response(item, is_deletable=item.id not in joined_ids) for item in items], total

    async def get_challenge(self, challenge_id: int) -> ChallengeResponse:
        challenge = await self.challenges.get(challenge_id)
        if challenge is None:
            raise ChallengeNotFoundError()
        return self.challenge_response(challenge)

    async def update_challenge(
        self,
        challenge_id: int,
        data: ChallengeUpdateRequest,
        admin_id: int,
    ) -> ChallengeResponse:
        challenge = await self.challenges.get(challenge_id)
        if challenge is None:
            raise ChallengeNotFoundError()
        values = data.model_dump(exclude_unset=True)
        await self._validate_challenge_relations(values)
        start = values.get("recruit_start_at", challenge.recruit_start_at)
        end = values.get("recruit_end_at", challenge.recruit_end_at)
        if end <= start:
            raise ValueError("모집 종료 일시는 모집 시작 일시보다 늦어야 합니다.")
        for key, value in values.items():
            setattr(challenge, key, value)
        challenge.updated_by_admin_id = admin_id
        await challenge.save()
        return self.challenge_response(challenge)

    async def delete_challenge(self, challenge_id: int, admin_id: int) -> None:
        challenge = await self.challenges.get(challenge_id)
        if challenge is None:
            raise ChallengeNotFoundError()
        if await UserChallenge.filter(challenge_id=challenge_id).exists():
            raise ChallengeInUseError()
        challenge.is_deleted = True
        challenge.is_displayed = False
        challenge.deleted_at = datetime.now(config.TIMEZONE)
        challenge.updated_by_admin_id = admin_id
        await challenge.save()

    async def create_custom_template(
        self,
        data: CustomChallengeTemplateCreateRequest,
        admin_id: int,
    ) -> CustomChallengeTemplateResponse:
        await self._validate_common_code(data.check_type_id, "CST_CHK_TYPE")
        values = data.model_dump()
        challenge_type = values.pop("challenge_type")
        if challenge_type is not None:
            await self._validate_common_code(challenge_type, "CST_CHL_TYPE")
        values["challenge_type_id"] = challenge_type
        reward_badge_id = values.get("reward_badge_id")
        if reward_badge_id is not None and not await Badge.filter(id=reward_badge_id, is_active=True).exists():
            raise BadgeNotFoundError()
        values["name"] = values["name"].strip()
        try:
            template = await CustomChallengeTemplate.create(
                **values,
                created_by_admin_id=admin_id,
            )
        except IntegrityError as error:
            raise CustomChallengeTemplateNameAlreadyExistsError() from error
        return self.custom_template_response(template)

    async def list_custom_templates(
        self,
        query: CustomChallengeTemplateAdminListQuery,
    ) -> tuple[list[CustomChallengeTemplateResponse], int]:
        items, total = await self.custom_templates.list(**query.model_dump())
        return [self.custom_template_response(item) for item in items], total

    async def get_custom_template(self, template_id: int) -> CustomChallengeTemplateResponse:
        template = await self.custom_templates.get(template_id)
        if template is None:
            raise CustomChallengeTemplateNotFoundError()
        return self.custom_template_response(template)

    async def update_custom_template(
        self,
        template_id: int,
        data: CustomChallengeTemplateUpdateRequest,
        admin_id: int,
    ) -> CustomChallengeTemplateResponse:
        template = await self.custom_templates.get(template_id)
        if template is None:
            raise CustomChallengeTemplateNotFoundError()
        values = data.model_dump(exclude_unset=True)
        if "check_type_id" in values:
            await self._validate_common_code(values["check_type_id"], "CST_CHK_TYPE")
        if "challenge_type" in values:
            challenge_type = values.pop("challenge_type")
            if challenge_type is not None:
                await self._validate_common_code(challenge_type, "CST_CHL_TYPE")
            values["challenge_type_id"] = challenge_type
        if "reward_badge_id" in values:
            reward_badge_id = values["reward_badge_id"]
            if reward_badge_id is not None and not await Badge.filter(id=reward_badge_id, is_active=True).exists():
                raise BadgeNotFoundError()
        if "name" in values:
            values["name"] = values["name"].strip()
        for key, value in values.items():
            setattr(template, key, value)
        template.updated_by_admin_id = admin_id
        try:
            await template.save()
        except IntegrityError as error:
            raise CustomChallengeTemplateNameAlreadyExistsError() from error
        return self.custom_template_response(template)

    async def _validate_challenge_relations(self, values: dict) -> None:
        for field_name, group_code in _COMMON_CODE_GROUPS.items():
            code_id = values.get(field_name)
            if code_id is None:
                continue
            code = await CommonCode.get_or_none(id=code_id, is_active=True).prefetch_related("group")
            if (
                code is None
                or not code.group.is_active
                or code.group.category != "CHL"
                or code.group.group_code != group_code
            ):
                raise InvalidCommonCodeError(f"{group_code} 공통코드를 확인해 주세요.")
        reward_badge_id = values.get("reward_badge_id")
        if reward_badge_id is not None and not await Badge.filter(id=reward_badge_id, is_active=True).exists():
            raise BadgeNotFoundError()

    @staticmethod
    async def _validate_common_code(code_id: int, group_code: str) -> None:
        code = await CommonCode.get_or_none(id=code_id, is_active=True).prefetch_related("group")
        if (
            code is None
            or not code.group.is_active
            or code.group.category != "CHL"
            or code.group.group_code != group_code
        ):
            raise InvalidCommonCodeError(f"{group_code} 공통코드를 확인해 주세요.")

    @staticmethod
    def badge_response(badge: Badge, *, is_deletable: bool = True) -> BadgeResponse:
        response = BadgeResponse.model_validate(badge)
        return response.model_copy(update={"is_deletable": is_deletable})

    @staticmethod
    def challenge_response(
        challenge: Challenge,
        *,
        is_deletable: bool = True,
    ) -> ChallengeResponse:
        response = ChallengeResponse.model_validate(challenge)
        return response.model_copy(update={"is_deletable": is_deletable})

    @staticmethod
    def custom_template_response(
        template: CustomChallengeTemplate,
    ) -> CustomChallengeTemplateResponse:
        return CustomChallengeTemplateResponse.model_validate(template)
