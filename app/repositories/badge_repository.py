from app.models.challenges import Badge


class BadgeRepository:
    async def get(self, badge_id: int) -> Badge | None:
        return await Badge.get_or_none(id=badge_id)

    async def list(
        self,
        *,
        badge_id: int | None = None,
        name: str | None = None,
        is_active: bool | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[Badge], int]:
        query = Badge.all()
        if badge_id is not None:
            query = query.filter(id=badge_id)
        if name:
            query = query.filter(name__icontains=name.strip())
        if is_active is not None:
            query = query.filter(is_active=is_active)
        return list(await query.order_by("-created_at").offset(offset).limit(limit)), await query.count()
