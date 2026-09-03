from app.dtos.common_codes import CommonCodeGroupListQuery, CommonCodeListQuery
from app.models.common_codes import CommonCode, CommonCodeGroup


class CommonCodeRepository:
    async def list_groups(self, query: CommonCodeGroupListQuery) -> tuple[list[CommonCodeGroup], int]:
        queryset = CommonCodeGroup.all()
        if query.category:
            queryset = queryset.filter(category=query.category)
        if query.group_code:
            queryset = queryset.filter(group_code__icontains=query.group_code)
        if query.group_name:
            queryset = queryset.filter(group_name__icontains=query.group_name.strip())
        if query.is_active is not None:
            queryset = queryset.filter(is_active=query.is_active)
        total = await queryset.count()
        items = await queryset.order_by("category", "group_code", "id").offset(query.offset).limit(query.limit)
        return items, total

    async def get_group(self, group_id: int) -> CommonCodeGroup | None:
        return await CommonCodeGroup.get_or_none(id=group_id)

    async def get_active_group(self, category: str, group_code: str) -> CommonCodeGroup | None:
        return await CommonCodeGroup.get_or_none(category=category, group_code=group_code, is_active=True)

    async def create_group(self, **values: object) -> CommonCodeGroup:
        return await CommonCodeGroup.create(**values)

    async def list_codes(self, group_id: int, query: CommonCodeListQuery) -> tuple[list[CommonCode], int]:
        queryset = CommonCode.filter(group_id=group_id)
        if query.detail_code:
            queryset = queryset.filter(detail_code__icontains=query.detail_code)
        if query.detail_name:
            queryset = queryset.filter(detail_name__icontains=query.detail_name.strip())
        if query.is_active is not None:
            queryset = queryset.filter(is_active=query.is_active)
        total = await queryset.count()
        items = await queryset.order_by("sort_order", "id").offset(query.offset).limit(query.limit)
        return items, total

    async def get_code(self, code_id: int) -> CommonCode | None:
        return await CommonCode.get_or_none(id=code_id)

    async def create_code(self, **values: object) -> CommonCode:
        return await CommonCode.create(**values)

    async def list_active_codes(self, group_id: int) -> list[CommonCode]:
        return await CommonCode.filter(group_id=group_id, is_active=True).order_by("sort_order", "id")

    async def active_code_exists(self, *, category: str, group_code: str, detail_code: str) -> bool:
        return await CommonCode.filter(
            group__category=category,
            group__group_code=group_code,
            group__is_active=True,
            detail_code=detail_code,
            is_active=True,
        ).exists()
