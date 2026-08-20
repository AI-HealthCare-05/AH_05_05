from collections.abc import Mapping
from typing import Protocol

from pydantic import ValidationError

from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexRequest,
    PublicGuidelineIndexResult,
)


class PublicGuidelineIndexer(Protocol):
    async def execute(
        self,
        request: PublicGuidelineIndexRequest,
    ) -> PublicGuidelineIndexResult: ...


class InvalidPublicGuidelineIndexMessageError(ValueError):
    """Redis 인덱싱 메시지가 계약과 다를 때 발생합니다."""


class PublicGuidelineIndexTask:
    def __init__(
        self,
        service: PublicGuidelineIndexer,
    ) -> None:
        self._service = service

    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        try:
            request = PublicGuidelineIndexRequest.model_validate(dict(message))
        except ValidationError as error:
            raise (
                InvalidPublicGuidelineIndexMessageError("Redis 공공 가이드라인 인덱싱 메시지가 올바르지 않습니다.")
            ) from error

        return await self._service.execute(request)
