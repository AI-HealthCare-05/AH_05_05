from pathlib import Path

import pytest

from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexRequest,
    PublicGuidelineIndexResult,
)
from ai_worker.tasks.public_guideline_index_task import (
    InvalidPublicGuidelineIndexMessageError,
    PublicGuidelineIndexTask,
)


class FakePublicGuidelineIndexService:
    def __init__(self) -> None:
        self.received_request: PublicGuidelineIndexRequest | None = None

    async def execute(
        self,
        request: PublicGuidelineIndexRequest,
    ) -> PublicGuidelineIndexResult:
        self.received_request = request

        return PublicGuidelineIndexResult(
            job_id=request.job_id,
            indexed_document_count=1,
            indexed_chunk_count=2,
            point_ids_by_document={
                "stroke-2020": [
                    "point-1",
                    "point-2",
                ]
            },
        )


class FailingPublicGuidelineIndexService:
    async def execute(
        self,
        request: PublicGuidelineIndexRequest,
    ) -> PublicGuidelineIndexResult:
        raise RuntimeError("OpenAI 임베딩 호출 실패")


async def test_execute_validates_message_and_runs_service() -> None:
    service = FakePublicGuidelineIndexService()
    task = PublicGuidelineIndexTask(service=service)

    result = await task.execute(
        {
            "job_id": "index-job-1",
            "job_type": ("PUBLIC_GUIDELINE_INDEX"),
            "manifest_path": ("data/public_guidelines/manifest.json"),
            "chunk_size": "800",
            "chunk_overlap": "100",
        }
    )

    assert service.received_request is not None
    assert service.received_request.job_id == "index-job-1"
    assert service.received_request.manifest_path == Path("data/public_guidelines/manifest.json")
    assert service.received_request.chunk_size == 800
    assert service.received_request.chunk_overlap == 100

    assert result.job_id == "index-job-1"
    assert result.indexed_document_count == 1
    assert result.indexed_chunk_count == 2


async def test_execute_rejects_invalid_message() -> None:
    service = FakePublicGuidelineIndexService()
    task = PublicGuidelineIndexTask(service=service)

    with pytest.raises(
        InvalidPublicGuidelineIndexMessageError,
        match="Redis",
    ):
        await task.execute(
            {
                "job_id": "index-job-1",
                "job_type": ("PUBLIC_GUIDELINE_INDEX"),
                # manifest_path 누락
                "chunk_size": "1000",
                "chunk_overlap": "200",
            }
        )

    assert service.received_request is None


async def test_execute_propagates_service_failure() -> None:
    task = PublicGuidelineIndexTask(service=(FailingPublicGuidelineIndexService()))

    with pytest.raises(
        RuntimeError,
        match="OpenAI 임베딩 호출 실패",
    ):
        await task.execute(
            {
                "job_id": "index-job-1",
                "job_type": ("PUBLIC_GUIDELINE_INDEX"),
                "manifest_path": ("data/public_guidelines/manifest.json"),
                "chunk_size": "1000",
                "chunk_overlap": "200",
            }
        )
