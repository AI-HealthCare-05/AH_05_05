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
    ) -> None:
        self.messages = messages or []
        self.group_create_error = group_create_error

        self.group_create_calls: list[dict[str, object]] = []
        self.read_calls: list[dict[str, object]] = []
        self.ack_calls: list[tuple[str, str, str]] = []

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
