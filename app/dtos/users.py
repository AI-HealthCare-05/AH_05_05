from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.core.validators import optional_after_validator, validate_phone_number
from app.dtos.base import BaseSerializerModel
from app.models.enums import AccountStatus


class UserUpdateRequest(BaseModel):
    name: Annotated[str | None, Field(None, min_length=2, max_length=100)]
    email: Annotated[
        EmailStr | None,
        Field(None, max_length=255),
    ]
    phone_number: Annotated[
        str | None,
        Field(None, description="Available Format: +8201011112222, 01011112222, 010-1111-2222"),
        optional_after_validator(validate_phone_number),
    ]
class UserInfoResponse(BaseSerializerModel):
    id: int
    name: str
    email: str
    phone_number: Annotated[str | None, Field(validation_alias="phone")]
    status: AccountStatus
    created_at: datetime
