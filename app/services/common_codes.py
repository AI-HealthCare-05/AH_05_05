import re

from tortoise.exceptions import IntegrityError

from app.core.exceptions import (
    CommonCodeAlreadyExistsError,
    CommonCodeGroupNotFoundError,
    CommonCodeNotFoundError,
    InvalidCommonCodeError,
)
from app.dtos.common_codes import (
    CommonCodeCreateRequest,
    CommonCodeGroupCreateRequest,
    CommonCodeGroupListQuery,
    CommonCodeGroupUpdateRequest,
    CommonCodeListQuery,
    CommonCodeUpdateRequest,
)
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.repositories.common_code_repository import CommonCodeRepository

COMMON_CODE_RE = re.compile(r"^[A-Z0-9_]+$")
COMMON_GROUP_CODE_RE = re.compile(r"^[A-Z0-9_]+$")


def normalize_common_code(value: str) -> str:
    normalized = value.strip().upper()
    if not COMMON_CODE_RE.fullmatch(normalized):
        raise InvalidCommonCodeError()
    return normalized


def normalize_common_group_code(value: str) -> str:
    normalized = value.strip().upper()
    if not COMMON_GROUP_CODE_RE.fullmatch(normalized):
        raise InvalidCommonCodeError()
    return normalized


class CommonCodeService:
    def __init__(self, repository: CommonCodeRepository | None = None) -> None:
        self.repository = repository or CommonCodeRepository()

    async def list_groups(self, query: CommonCodeGroupListQuery) -> tuple[list[CommonCodeGroup], int]:
        if query.category:
            query.category = normalize_common_group_code(query.category)
        if query.group_code:
            query.group_code = normalize_common_group_code(query.group_code)
        return await self.repository.list_groups(query)

    async def get_group(self, group_id: int) -> CommonCodeGroup:
        group = await self.repository.get_group(group_id)
        if group is None:
            raise CommonCodeGroupNotFoundError()
        return group

    async def create_group(self, request: CommonCodeGroupCreateRequest, actor_admin_id: int) -> CommonCodeGroup:
        try:
            return await self.repository.create_group(
                category=normalize_common_group_code(request.category),
                group_code=normalize_common_group_code(request.group_code),
                group_name=request.group_name,
                description=request.description or None,
                is_active=request.is_active,
                created_by_admin_id=actor_admin_id,
                updated_by_admin_id=actor_admin_id,
            )
        except IntegrityError as error:
            raise CommonCodeAlreadyExistsError() from error

    async def update_group(
        self,
        group_id: int,
        request: CommonCodeGroupUpdateRequest,
        actor_admin_id: int,
    ) -> CommonCodeGroup:
        group = await self.get_group(group_id)
        update_fields: list[str] = []
        for field_name in ("category", "group_name", "description", "is_active"):
            if field_name not in request.model_fields_set:
                continue
            value = getattr(request, field_name)
            if field_name == "category" and value is not None:
                value = normalize_common_group_code(value)
            setattr(group, field_name, value)
            update_fields.append(field_name)
        group.updated_by_admin_id = actor_admin_id
        update_fields.extend(("updated_by_admin_id", "updated_at"))
        await group.save(update_fields=update_fields)
        return group

    async def list_codes(self, group_id: int, query: CommonCodeListQuery) -> tuple[list[CommonCode], int]:
        await self.get_group(group_id)
        if query.detail_code:
            query.detail_code = normalize_common_code(query.detail_code)
        return await self.repository.list_codes(group_id, query)

    async def get_code(self, code_id: int) -> CommonCode:
        code = await self.repository.get_code(code_id)
        if code is None:
            raise CommonCodeNotFoundError()
        return code

    async def create_code(
        self,
        group_id: int,
        request: CommonCodeCreateRequest,
        actor_admin_id: int,
    ) -> CommonCode:
        await self.get_group(group_id)
        try:
            return await self.repository.create_code(
                group_id=group_id,
                detail_code=normalize_common_code(request.detail_code),
                detail_name=request.detail_name,
                description=request.description or None,
                sort_order=request.sort_order,
                is_active=request.is_active,
                created_by_admin_id=actor_admin_id,
                updated_by_admin_id=actor_admin_id,
            )
        except IntegrityError as error:
            raise CommonCodeAlreadyExistsError() from error

    async def update_code(
        self,
        code_id: int,
        request: CommonCodeUpdateRequest,
        actor_admin_id: int,
    ) -> CommonCode:
        code = await self.get_code(code_id)
        update_fields: list[str] = []
        for field_name in ("detail_name", "description", "sort_order", "is_active"):
            if field_name not in request.model_fields_set:
                continue
            setattr(code, field_name, getattr(request, field_name))
            update_fields.append(field_name)
        code.updated_by_admin_id = actor_admin_id
        update_fields.extend(("updated_by_admin_id", "updated_at"))
        await code.save(update_fields=update_fields)
        return code

    async def list_active_codes(self, category: str, group_code: str) -> tuple[CommonCodeGroup, list[CommonCode]]:
        group = await self.repository.get_active_group(
            normalize_common_group_code(category),
            normalize_common_group_code(group_code),
        )
        if group is None:
            raise CommonCodeGroupNotFoundError()
        return group, await self.repository.list_active_codes(group.id)

    async def is_active_code(self, category: str, group_code: str, detail_code: str) -> bool:
        return await self.repository.active_code_exists(
            category=normalize_common_group_code(category),
            group_code=normalize_common_group_code(group_code),
            detail_code=normalize_common_code(detail_code),
        )
