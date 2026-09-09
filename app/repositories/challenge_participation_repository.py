from app.models.challenges import ChallengeVerification, UserBadge, UserChallenge


class ChallengeParticipationRepository:
    async def get_owned(self, participation_id: int, user_id: int) -> UserChallenge | None:
        return await UserChallenge.get_or_none(id=participation_id, user_id=user_id)

    async def list_owned(self, user_id: int) -> list[UserChallenge]:
        return list(await UserChallenge.filter(user_id=user_id).order_by("-joined_at", "-id"))

    async def get_verification(self, verification_id: int) -> ChallengeVerification | None:
        return await ChallengeVerification.get_or_none(id=verification_id)

    async def list_badges(self, user_id: int) -> list[UserBadge]:
        return list(await UserBadge.filter(user_id=user_id).order_by("-awarded_at"))
