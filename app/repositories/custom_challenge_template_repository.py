from app.models.challenges import CustomChallengeTemplate


class CustomChallengeTemplateRepository:
    async def get(self, template_id: int) -> CustomChallengeTemplate | None:
        return await CustomChallengeTemplate.get_or_none(id=template_id)

    async def list(
        self,
        *,
        template_id: int | None = None,
        name: str | None = None,
        challenge_type: int | None = None,
        check_type_id: int | None = None,
        reward_badge_id: int | None = None,
        is_active: bool | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[CustomChallengeTemplate], int]:
        query = CustomChallengeTemplate.all()
        if template_id is not None:
            query = query.filter(id=template_id)
        if name:
            query = query.filter(name__icontains=name.strip())
        if challenge_type is not None:
            query = query.filter(challenge_type_id=challenge_type)
        if check_type_id is not None:
            query = query.filter(check_type_id=check_type_id)
        if reward_badge_id is not None:
            query = query.filter(reward_badge_id=reward_badge_id)
        if is_active is not None:
            query = query.filter(is_active=is_active)
        return list(await query.order_by("-created_at").offset(offset).limit(limit)), await query.count()
