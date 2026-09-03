from datetime import datetime

from pydantic import Field, field_validator

from app.dtos.base import BaseSerializerModel

COMMON_CODE_PATTERN = r"^[A-Z0-9_]+$"
DETAIL_CODE_PATTERN = r"^[A-Z0-9_]+$"


def normalize_code_value(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class CommonCodeGroupListQuery(BaseSerializerModel):
    category: str | None = Field(default=None, max_length=20, pattern=COMMON_CODE_PATTERN)
    group_code: str | None = Field(default=None, max_length=20, pattern=COMMON_CODE_PATTERN)
    group_name: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("category", "group_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: object) -> object:
        return normalize_code_value(value)


class CommonCodeGroupCreateRequest(BaseSerializerModel):
    category: str = Field(min_length=1, max_length=20, pattern=COMMON_CODE_PATTERN)
    group_code: str = Field(min_length=1, max_length=20, pattern=COMMON_CODE_PATTERN)
    group_name: str = Field(min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    is_active: bool = True

    @field_validator("category", "group_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: object) -> object:
        return normalize_code_value(value)

    @field_validator("group_name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CommonCodeGroupUpdateRequest(BaseSerializerModel):
    category: str | None = Field(default=None, min_length=1, max_length=20, pattern=COMMON_CODE_PATTERN)
    group_name: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> object:
        return normalize_code_value(value)

    @field_validator("group_name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CommonCodeGroupResponse(BaseSerializerModel):
    id: int
    category: str
    group_code: str
    group_name: str
    description: str | None
    is_active: bool
    created_by_admin_id: int | None
    updated_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None


class CommonCodeGroupListResponse(BaseSerializerModel):
    total_count: int
    offset: int
    limit: int
    items: list[CommonCodeGroupResponse]


class CommonCodeListQuery(BaseSerializerModel):
    detail_code: str | None = Field(default=None, max_length=20)
    detail_name: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("detail_code", mode="before")
    @classmethod
    def normalize_detail_code(cls, value: object) -> object:
        return normalize_code_value(value)


class CommonCodeCreateRequest(BaseSerializerModel):
    detail_code: str = Field(min_length=1, max_length=20, pattern=DETAIL_CODE_PATTERN)
    detail_name: str = Field(min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    sort_order: int = Field(default=0, ge=0, le=99)
    is_active: bool = True

    @field_validator("detail_code", mode="before")
    @classmethod
    def normalize_detail_code(cls, value: object) -> object:
        return normalize_code_value(value)

    @field_validator("detail_name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CommonCodeUpdateRequest(BaseSerializerModel):
    detail_name: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    sort_order: int | None = Field(default=None, ge=0, le=99)
    is_active: bool | None = None

    @field_validator("detail_name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CommonCodeResponse(BaseSerializerModel):
    id: int
    group_id: int
    detail_code: str
    detail_name: str
    description: str | None
    sort_order: int
    is_active: bool
    created_by_admin_id: int | None
    updated_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None


class CommonCodeListResponse(BaseSerializerModel):
    total_count: int
    offset: int
    limit: int
    items: list[CommonCodeResponse]


class CommonCodeLookupItem(BaseSerializerModel):
    id: int
    detail_code: str
    detail_name: str
    sort_order: int


class CommonCodeLookupResponse(BaseSerializerModel):
    category: str
    group_code: str
    group_name: str
    items: list[CommonCodeLookupItem]
