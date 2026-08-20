import logging
from collections.abc import Mapping
from typing import Protocol

from redis.exceptions import ResponseError

from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexResult,
)
from ai_worker.tasks.public_guideline_index_task import (
    InvalidPublicGuidelineIndexMessageError,
)

RedisStreamMessages = list[
    tuple[
        str,
        list[
            tuple[
                str,
                dict[str, str],
            ]
        ],
    ]
]


class RedisStreamClient(Protocol):
    async def xgroup_create(
        self,
        *,
        name: str,
        groupname: str,
        id: str,
        mkstream: bool,
    ) -> object: ...

    async def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> RedisStreamMessages: ...

    async def xack(
        self,
        name: str,
        groupname: str,
        message_id: str,
    ) -> int: ...


class PublicGuidelineIndexTaskProtocol(Protocol):
    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult: ...


class PublicGuidelineIndexWorker:
    def __init__(
        self,
        *,
        redis_client: RedisStreamClient,
        task: PublicGuidelineIndexTaskProtocol,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        read_count: int = 1,
        block_ms: int = 5000,
        logger: logging.Logger | None = None,
    ) -> None:
        self._redis_client = redis_client
        self._task = task
        self._stream_name = stream_name
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        self._read_count = read_count
        self._block_ms = block_ms
        self._logger = logger or logging.getLogger(__name__)

    async def ensure_consumer_group(
        self,
    ) -> None:
        try:
            await self._redis_client.xgroup_create(
                name=self._stream_name,
                groupname=self._consumer_group,
                id="0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def run_once(
        self,
    ) -> bool:
        streams = await self._redis_client.xreadgroup(
            groupname=self._consumer_group,
            consumername=self._consumer_name,
            streams={
                self._stream_name: ">",
            },
            count=self._read_count,
            block=self._block_ms,
        )

        if not streams:
            return False

        for _, messages in streams:
            for message_id, message in messages:
                await self._process_message(
                    message_id=message_id,
                    message=message,
                )

        return True

    async def run_forever(
        self,
    ) -> None:
        await self.ensure_consumer_group()

        while True:
            await self.run_once()

    async def _process_message(
        self,
        *,
        message_id: str,
        message: Mapping[str, str],
    ) -> None:
        try:
            result = await self._task.execute(message)
        except InvalidPublicGuidelineIndexMessageError as error:
            self._logger.error(
                "잘못된 인덱싱 메시지를 제외합니다: message_id=%s, error=%s",
                message_id,
                error,
            )
            await self._acknowledge(message_id)
        except Exception:
            self._logger.exception(
                "공공 가이드라인 인덱싱에 실패했습니다. 메시지를 Pending 상태로 유지합니다: message_id=%s",
                message_id,
            )
        else:
            self._logger.info(
                "공공 가이드라인 인덱싱 완료: job_id=%s, documents=%s, chunks=%s",
                result.job_id,
                result.indexed_document_count,
                result.indexed_chunk_count,
            )
            await self._acknowledge(message_id)

    async def _acknowledge(
        self,
        message_id: str,
    ) -> None:
        await self._redis_client.xack(
            self._stream_name,
            self._consumer_group,
            message_id,
        )
