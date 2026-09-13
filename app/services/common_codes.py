import re

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.exceptions import (
    CommonCodeAlreadyExistsError,
    CommonCodeGroupInUseError,
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
from app.models.challenges import Badge, Challenge, CustomChallengeTemplate
from app.models.chat import ChatSession
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
        groups, total = await self.repository.list_groups(query)
        used_group_ids = await self._used_group_ids(groups)
        for group in groups:
            group.can_delete = group.id not in used_group_ids
        return groups, total

    async def get_group(self, group_id: int) -> CommonCodeGroup:
        group = await self.repository.get_group(group_id)
        if group is None:
            raise CommonCodeGroupNotFoundError()
        group.can_delete = group.id not in await self._used_group_ids([group])
        return group

    async def delete_group(self, group_id: int) -> None:
        try:
            async with in_transaction() as connection:
                group = await CommonCodeGroup.filter(id=group_id).using_db(connection).select_for_update().first()
                if group is None:
                    raise CommonCodeGroupNotFoundError()
                if group.id in await self._used_group_ids([group], connection):
                    raise CommonCodeGroupInUseError()
                await CommonCode.filter(group_id=group.id).using_db(connection).delete()
                await group.delete(using_db=connection)
        except IntegrityError as error:
            raise CommonCodeGroupInUseError() from error

    @staticmethod
    async def _used_group_ids(
        groups: list[CommonCodeGroup],
        connection: BaseDBAsyncClient | None = None,
    ) -> set[int]:
        if not groups:
            return set()

        group_ids = [group.id for group in groups]
        codes_query = CommonCode.filter(group_id__in=group_ids)
        if connection is not None:
            codes_query = codes_query.using_db(connection)
        code_rows = await codes_query.values("id", "group_id", "detail_code")
        if not code_rows:
            return set()

        code_to_group = {row["id"]: row["group_id"] for row in code_rows}
        code_ids = list(code_to_group)
        used_code_ids: set[int] = set()

        reference_queries = (
            (Badge.filter(type_id__in=code_ids), "type_id"),
            (Challenge.filter(challenge_type_id__in=code_ids), "challenge_type_id"),
            (Challenge.filter(challenge_period_id__in=code_ids), "challenge_period_id"),
            (Challenge.filter(check_type_id__in=code_ids), "check_type_id"),
            (Challenge.filter(check_frequency_id__in=code_ids), "check_frequency_id"),
            (CustomChallengeTemplate.filter(check_type_id__in=code_ids), "check_type_id"),
            (CustomChallengeTemplate.filter(challenge_type_id__in=code_ids), "challenge_type_id"),
        )
        for query, field_name in reference_queries:
            if connection is not None:
                query = query.using_db(connection)
            used_code_ids.update(await query.values_list(field_name, flat=True))

        reason_groups = {
            (group.category, group.group_code): group.id
            for group in groups
            if group.category == "CHAT" and group.group_code in {"P_REASON", "N_REASON"}
        }
        if reason_groups:
            reason_codes = [row["detail_code"] for row in code_rows if row["group_id"] in reason_groups.values()]
            chat_query = ChatSession.filter(reason_code__in=reason_codes)
            if connection is not None:
                chat_query = chat_query.using_db(connection)
            detail_groups = {
                (row["group_id"], row["detail_code"]) for row in code_rows if row["group_id"] in reason_groups.values()
            }
            for row in await chat_query.values("reason_code", "is_like"):
                group_code = "P_REASON" if row["is_like"] is True else "N_REASON" if row["is_like"] is False else None
                group_id = reason_groups.get(("CHAT", group_code)) if group_code else None
                if group_id is not None and (group_id, row["reason_code"]) in detail_groups:
                    used_code_ids.update(
                        code_id for code_id, mapped_group_id in code_to_group.items() if mapped_group_id == group_id
                    )

        return {code_to_group[code_id] for code_id in used_code_ids}

    async def create_group(self, request: CommonCodeGroupCreateRequest, actor_admin_id: int) -> CommonCodeGroup:
        try:
            group = await self.repository.create_group(
                category=normalize_common_group_code(request.category),
                group_code=normalize_common_group_code(request.group_code),
                group_name=request.group_name,
                description=request.description or None,
                is_active=request.is_active,
                created_by_admin_id=actor_admin_id,
                updated_by_admin_id=actor_admin_id,
            )
            group.can_delete = True
            return group
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
