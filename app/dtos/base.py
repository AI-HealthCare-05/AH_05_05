from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseSerializerModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CamelModel(BaseModel):
    """요청·응답 공통 베이스. 파이썬은 snake_case로 쓰고 JSON은 camelCase로 주고받는다.

    회의 확정 규칙(A-2)이며 프론트 타입(frontend/src/entities/*/types.ts)이 이미 camelCase다.
    기존 인증·사용자 DTO는 아직 snake_case를 노출하므로 이관 대상으로 남아 있다.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
