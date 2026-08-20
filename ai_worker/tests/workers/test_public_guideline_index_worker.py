import asyncio
from collections.abc import Mapping

from redis.exceptions import ResponseError

from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexResult,
)
from ai_worker.tasks.public_guideline_index_task import (
    InvalidPublicGuidelineIndexMessageError,
)
from ai_worker.workers.public_guideline_index_worker import (
    PublicGuidelineIndexWorker,
)


class FakeRedisStreamClient:
    def __init__(
        self,
        messages: list[
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
        | None = None,
        group_create_error: Exception | None = None,
        reclaimed_messages: list[tuple[str, dict[str, str]]] | None = None,
        delivery_count: int = 1,
        next_claim_cursor: str = "0-0",
    ) -> None:
        self.messages = messages or []
        self.group_create_error = group_create_error
        self.reclaimed_messages = reclaimed_messages or []
        self.delivery_count = delivery_count
        self.next_claim_cursor = next_claim_cursor

        self.group_create_calls: list[dict[str, object]] = []
        self.read_calls: list[dict[str, object]] = []
        self.ack_calls: list[tuple[str, str, str]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.pending_calls: list[dict[str, object]] = []
        self.add_calls: list[tuple[str, dict[str, str]]] = []
        self.lease_refresh_calls: list[dict[str, object]] = []
        self.eval_calls: list[tuple[object, ...]] = []
        self.set_calls: list[dict[str, object]] = []

    async def xgroup_create(
        self,
        *,
        name: str,
        groupname: str,
        id: str,
        mkstream: bool,
    ) -> bool:
        self.group_create_calls.append(
            {
                "name": name,
                "groupname": groupname,
                "id": id,
                "mkstream": mkstream,
            }
        )

        if self.group_create_error is not None:
            raise self.group_create_error

        return True

    async def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> list[
        tuple[
            str,
            list[
                tuple[
                    str,
                    dict[str, str],
                ]
            ],
        ]
    ]:
        self.read_calls.append(
            {
                "groupname": groupname,
                "consumername": consumername,
                "streams": streams,
                "count": count,
                "block": block,
            }
        )

        return self.messages

    async def xack(
        self,
        name: str,
        groupname: str,
        message_id: str,
    ) -> int:
        self.ack_calls.append(
            (
                name,
                groupname,
                message_id,
            )
        )
        return 1

    async def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
        self.claim_calls.append(
            {
                "name": name,
                "groupname": groupname,
                "consumername": consumername,
                "min_idle_time": min_idle_time,
                "start_id": start_id,
                "count": count,
            }
        )
        return self.next_claim_cursor, self.reclaimed_messages, []

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
    ) -> list[str]:
        self.lease_refresh_calls.append(
            {
                "name": name,
                "groupname": groupname,
                "consumername": consumername,
                "min_idle_time": min_idle_time,
                "message_ids": message_ids,
                "idle": idle,
                "justid": justid,
            }
        )
        return message_ids

    async def xpending_range(
        self,
        name: str,
        groupname: str,
        min: str,
        max: str,
        count: int,
    ) -> list[dict[str, object]]:
        self.pending_calls.append(
            {
                "name": name,
                "groupname": groupname,
                "min": min,
                "max": max,
                "count": count,
            }
        )
        return [
            {
                "message_id": min,
                "times_delivered": self.delivery_count,
            }
        ]

    async def xadd(
        self,
        name: str,
        fields: dict[str, str],
    ) -> str:
        self.add_calls.append((name, fields))
        return "2-0"

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> int:
        self.eval_calls.append((script, numkeys, *keys_and_args))
        if "XADD" not in script:
            return 1
        dead_letter_stream = str(keys_and_args[0])
        source_stream = str(keys_and_args[1])
        groupname = str(keys_and_args[2])
        message_id = str(keys_and_args[3])
        fields = {str(keys_and_args[index]): str(keys_and_args[index + 1]) for index in range(4, len(keys_and_args), 2)}
        self.add_calls.append((dead_letter_stream, fields))
        self.ack_calls.append((source_stream, groupname, message_id))
        return 1

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool,
        px: int,
    ) -> bool:
        self.set_calls.append(
            {
                "name": name,
                "value": value,
                "nx": nx,
                "px": px,
            }
        )
        return True


class SuccessfulTask:
    def __init__(self) -> None:
        self.received_message: Mapping[str, str] | None = None

    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        self.received_message = message

        return PublicGuidelineIndexResult(
            job_id=message["job_id"],
            indexed_document_count=1,
            indexed_chunk_count=2,
            point_ids_by_document={
                "stroke-2020": [
                    "point-1",
                    "point-2",
                ]
            },
        )


class InvalidMessageTask:
    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        raise (InvalidPublicGuidelineIndexMessageError("잘못된 메시지"))


class FailingTask:
    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        raise RuntimeError("OpenAI 임베딩 호출 실패")


class SlowSuccessfulTask(SuccessfulTask):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self,
        message: Mapping[str, str],
    ) -> PublicGuidelineIndexResult:
        self.started.set()
        await self.release.wait()
        return await super().execute(message)


def build_stream_messages() -> list[
    tuple[
        str,
        list[
            tuple[
                str,
                dict[str, str],
            ]
        ],
    ]
]:
    return [
        (
            "public-guideline-index-jobs",
            [
                (
                    "1-0",
                    {
                        "job_id": "index-job-1",
                        "job_type": ("PUBLIC_GUIDELINE_INDEX"),
                        "manifest_path": ("data/public_guidelines/manifest.json"),
                        "chunk_size": "1000",
                        "chunk_overlap": "200",
                    },
                )
            ],
        )
    ]


async def test_ensure_consumer_group_creates_group() -> None:
    redis_client = FakeRedisStreamClient()
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=SuccessfulTask(),
        stream_name=("public-guideline-index-jobs"),
        consumer_group=("public-guideline-index-workers"),
        consumer_name="worker-1",
    )

    await worker.ensure_consumer_group()

    assert redis_client.group_create_calls == [
        {
            "name": ("public-guideline-index-jobs"),
            "groupname": ("public-guideline-index-workers"),
            "id": "0",
            "mkstream": True,
        }
    ]


async def test_ensure_consumer_group_accepts_existing_group() -> None:
    redis_client = FakeRedisStreamClient(
        group_create_error=ResponseError("BUSYGROUP Consumer Group name already exists")
    )
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=SuccessfulTask(),
        stream_name=("public-guideline-index-jobs"),
        consumer_group=("public-guideline-index-workers"),
        consumer_name="worker-1",
    )

    await worker.ensure_consumer_group()


async def test_run_once_acknowledges_successful_message() -> None:
    redis_client = FakeRedisStreamClient(messages=build_stream_messages())
    task = SuccessfulTask()

    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=task,
        stream_name=("public-guideline-index-jobs"),
        consumer_group=("public-guideline-index-workers"),
        consumer_name="worker-1",
    )

    processed = await worker.run_once()

    assert processed is True
    assert task.received_message is not None
    assert task.received_message["job_id"] == "index-job-1"
    assert redis_client.ack_calls == [
        (
            "public-guideline-index-jobs",
            "public-guideline-index-workers",
            "1-0",
        )
    ]
    assert redis_client.set_calls[0]["name"] == ("public-guideline-index-jobs:index-lock")
    assert redis_client.set_calls[0]["nx"] is True


async def test_run_once_acknowledges_invalid_message() -> None:
    redis_client = FakeRedisStreamClient(messages=build_stream_messages())

    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=InvalidMessageTask(),
        stream_name=("public-guideline-index-jobs"),
        consumer_group=("public-guideline-index-workers"),
        consumer_name="worker-1",
    )

    processed = await worker.run_once()

    assert processed is True
    assert redis_client.ack_calls == [
        (
            "public-guideline-index-jobs",
            "public-guideline-index-workers",
            "1-0",
        )
    ]


async def test_run_once_keeps_failed_message_pending() -> None:
    redis_client = FakeRedisStreamClient(messages=build_stream_messages())

    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=FailingTask(),
        stream_name=("public-guideline-index-jobs"),
        consumer_group=("public-guideline-index-workers"),
        consumer_name="worker-1",
    )

    processed = await worker.run_once()

    assert processed is True
    assert redis_client.ack_calls == []
    assert redis_client.add_calls == []


async def test_run_once_reclaims_stale_pending_message() -> None:
    message_id, message = build_stream_messages()[0][1][0]
    redis_client = FakeRedisStreamClient(
        reclaimed_messages=[(message_id, message)],
        messages=[],
        delivery_count=2,
    )
    task = SuccessfulTask()
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=task,
        stream_name="public-guideline-index-jobs",
        consumer_group="public-guideline-index-workers",
        consumer_name="worker-2",
        claim_idle_ms=60_000,
        max_attempts=3,
        dead_letter_stream="public-guideline-index-jobs-dead",
    )

    processed = await worker.run_once()

    assert processed is True
    assert task.received_message == message
    assert redis_client.read_calls == []
    assert redis_client.ack_calls == [
        (
            "public-guideline-index-jobs",
            "public-guideline-index-workers",
            "1-0",
        )
    ]


async def test_run_once_moves_exhausted_message_to_dead_letter() -> None:
    message_id, message = build_stream_messages()[0][1][0]
    redis_client = FakeRedisStreamClient(
        reclaimed_messages=[(message_id, message)],
        delivery_count=3,
    )
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=FailingTask(),
        stream_name="public-guideline-index-jobs",
        consumer_group="public-guideline-index-workers",
        consumer_name="worker-2",
        claim_idle_ms=60_000,
        max_attempts=3,
        dead_letter_stream="public-guideline-index-jobs-dead",
    )

    processed = await worker.run_once()

    assert processed is True
    assert redis_client.add_calls == [
        (
            "public-guideline-index-jobs-dead",
            {
                **message,
                "original_message_id": "1-0",
                "failure_type": "RuntimeError",
                "failure_message": "OpenAI 임베딩 호출 실패",
            },
        )
    ]
    assert redis_client.ack_calls == [
        (
            "public-guideline-index-jobs",
            "public-guideline-index-workers",
            "1-0",
        )
    ]
    dead_letter_calls = [call for call in redis_client.eval_calls if "XADD" in str(call[0])]
    assert len(dead_letter_calls) == 1


async def test_run_once_continues_xautoclaim_from_returned_cursor() -> None:
    redis_client = FakeRedisStreamClient(
        messages=[],
        next_claim_cursor="9-0",
    )
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=SuccessfulTask(),
        stream_name="public-guideline-index-jobs",
        consumer_group="public-guideline-index-workers",
        consumer_name="worker-1",
    )

    await worker.run_once()
    redis_client.next_claim_cursor = "0-0"
    await worker.run_once()

    assert [call["start_id"] for call in redis_client.claim_calls] == [
        "0-0",
        "9-0",
    ]


async def test_run_once_refreshes_lease_during_long_task() -> None:
    redis_client = FakeRedisStreamClient(messages=build_stream_messages())
    task = SlowSuccessfulTask()
    worker = PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=task,
        stream_name="public-guideline-index-jobs",
        consumer_group="public-guideline-index-workers",
        consumer_name="worker-1",
        claim_idle_ms=30,
    )

    run_task = asyncio.create_task(worker.run_once())
    await task.started.wait()
    await asyncio.sleep(0.03)
    task.release.set()
    await run_task

    assert redis_client.lease_refresh_calls
    assert redis_client.lease_refresh_calls[0]["message_ids"] == ["1-0"]
    assert redis_client.lease_refresh_calls[0]["justid"] is True
