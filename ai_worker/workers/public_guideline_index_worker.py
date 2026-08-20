import asyncio
import logging
from collections.abc import Mapping
from contextlib import suppress
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
RedisClaimResponse = tuple[
    str,
    list[tuple[str, dict[str, str]]],
    list[str],
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

    async def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str,
        count: int,
    ) -> RedisClaimResponse: ...

    async def xpending_range(
        self,
        name: str,
        groupname: str,
        min: str,
        max: str,
        count: int,
    ) -> list[dict[str, object]]: ...

    async def xadd(
        self,
        name: str,
        fields: dict[str, str],
    ) -> str: ...

    async def xclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        message_ids: list[str],
        *,
        idle: int,
        justid: bool,
    ) -> list[str]: ...

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> int: ...

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool,
        px: int,
    ) -> bool | None: ...


class PublicGuidelineIndexTaskProtocol(Protocol):
    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult: ...


class PublicGuidelineIndexWorker:
    _MOVE_TO_DEAD_LETTER_SCRIPT = """
    redis.call('XADD', KEYS[1], '*', unpack(ARGV, 3))
    return redis.call('XACK', KEYS[2], ARGV[1], ARGV[2])
    """
    _EXTEND_LOCK_SCRIPT = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('PEXPIRE', KEYS[1], ARGV[2])
    end
    return 0
    """
    _RELEASE_LOCK_SCRIPT = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """

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
        claim_idle_ms: int = 60_000,
        max_attempts: int = 3,
        dead_letter_stream: str = "public-guideline-index-jobs-dead",
        logger: logging.Logger | None = None,
    ) -> None:
        if claim_idle_ms <= 0:
            raise ValueError("Pending 작업 회수 대기시간은 0보다 커야 합니다.")
        if max_attempts <= 0:
            raise ValueError("최대 처리 횟수는 0보다 커야 합니다.")
        if not dead_letter_stream.strip():
            raise ValueError("Dead Letter Stream 이름은 비어 있을 수 없습니다.")

        self._redis_client = redis_client
        self._task = task
        self._stream_name = stream_name
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        self._read_count = read_count
        self._block_ms = block_ms
        self._claim_idle_ms = claim_idle_ms
        self._max_attempts = max_attempts
        self._dead_letter_stream = dead_letter_stream.strip()
        self._claim_cursor = "0-0"
        self._lease_refresh_seconds = max(
            claim_idle_ms / 3000,
            0.001,
        )
        self._index_lock_name = f"{self._stream_name}:index-lock"
        self._index_lock_ttl_ms = max(claim_idle_ms * 2, 1000)
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
        reclaimed_messages = await self._claim_stale_messages()
        if reclaimed_messages:
            for message_id, message in reclaimed_messages:
                await self._process_message(
                    message_id=message_id,
                    message=message,
                )
            return True

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
            result = await self._execute_with_lease(
                message_id=message_id,
                message=message,
            )
        except InvalidPublicGuidelineIndexMessageError as error:
            self._logger.error(
                "잘못된 인덱싱 메시지를 제외합니다: message_id=%s, error=%s",
                message_id,
                error,
            )
            await self._acknowledge(message_id)
        except Exception as error:
            self._logger.exception(
                "공공 가이드라인 인덱싱에 실패했습니다. 메시지를 Pending 상태로 유지합니다: message_id=%s",
                message_id,
            )
            delivery_count = await self._get_delivery_count(message_id)
            if delivery_count >= self._max_attempts:
                await self._move_to_dead_letter(
                    message_id=message_id,
                    message=message,
                    error=error,
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

    async def _claim_stale_messages(
        self,
    ) -> list[tuple[str, dict[str, str]]]:
        response = await self._redis_client.xautoclaim(
            self._stream_name,
            self._consumer_group,
            self._consumer_name,
            self._claim_idle_ms,
            self._claim_cursor,
            self._read_count,
        )
        self._claim_cursor = response[0]
        return response[1]

    async def _execute_with_lease(
        self,
        *,
        message_id: str,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        lock_token = f"{self._consumer_name}:{message_id}"
        heartbeat = asyncio.create_task(
            self._refresh_lease(
                message_id=message_id,
                lock_token=lock_token,
            )
        )
        lock_acquired = False
        try:
            await self._acquire_index_lock(lock_token)
            lock_acquired = True
            return await self._task.execute(message)
        finally:
            try:
                if lock_acquired:
                    await self._release_index_lock(lock_token)
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

    async def _refresh_lease(
        self,
        message_id: str,
        lock_token: str,
    ) -> None:
        while True:
            await asyncio.sleep(self._lease_refresh_seconds)
            try:
                await self._redis_client.xclaim(
                    self._stream_name,
                    self._consumer_group,
                    self._consumer_name,
                    0,
                    [message_id],
                    idle=0,
                    justid=True,
                )
                await self._redis_client.eval(
                    self._EXTEND_LOCK_SCRIPT,
                    1,
                    self._index_lock_name,
                    lock_token,
                    self._index_lock_ttl_ms,
                )
            except Exception:
                self._logger.exception(
                    "인덱싱 작업의 Redis lease 갱신에 실패했습니다: message_id=%s",
                    message_id,
                )

    async def _acquire_index_lock(
        self,
        lock_token: str,
    ) -> None:
        while True:
            acquired = await self._redis_client.set(
                self._index_lock_name,
                lock_token,
                nx=True,
                px=self._index_lock_ttl_ms,
            )
            if acquired:
                return
            await asyncio.sleep(self._lease_refresh_seconds)

    async def _release_index_lock(
        self,
        lock_token: str,
    ) -> None:
        await self._redis_client.eval(
            self._RELEASE_LOCK_SCRIPT,
            1,
            self._index_lock_name,
            lock_token,
        )

    async def _get_delivery_count(
        self,
        message_id: str,
    ) -> int:
        pending_entries = await self._redis_client.xpending_range(
            self._stream_name,
            self._consumer_group,
            message_id,
            message_id,
            1,
        )
        if not pending_entries:
            return 1

        value = pending_entries[0].get("times_delivered", 1)
        return int(value)

    async def _move_to_dead_letter(
        self,
        *,
        message_id: str,
        message: Mapping[str, str],
        error: Exception,
    ) -> None:
        fields = {
            **dict(message),
            "original_message_id": message_id,
            "failure_type": type(error).__name__,
            "failure_message": str(error),
        }
        flattened_fields = [value for item in fields.items() for value in item]
        await self._redis_client.eval(
            self._MOVE_TO_DEAD_LETTER_SCRIPT,
            2,
            self._dead_letter_stream,
            self._stream_name,
            self._consumer_group,
            message_id,
            *flattened_fields,
        )
        self._logger.error(
            "최대 처리 횟수를 초과한 인덱싱 작업을 Dead Letter Stream으로 이동했습니다: message_id=%s, stream=%s",
            message_id,
            self._dead_letter_stream,
        )
