from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexRequest,
)


def test_request_accepts_public_guideline_index_job() -> None:
    request = PublicGuidelineIndexRequest(
        job_id="index-job-1",
        job_type="PUBLIC_GUIDELINE_INDEX",
        manifest_path=("data/public_guidelines/manifest.json"),
        chunk_size=1000,
        chunk_overlap=200,
    )

    assert request.job_id == "index-job-1"
    assert request.job_type == "PUBLIC_GUIDELINE_INDEX"
    assert request.manifest_path == Path("data/public_guidelines/manifest.json")
    assert request.chunk_size == 1000
    assert request.chunk_overlap == 200


def test_request_uses_default_chunk_settings() -> None:
    request = PublicGuidelineIndexRequest(
        job_id="index-job-1",
        manifest_path=("data/public_guidelines/manifest.json"),
    )

    assert request.chunk_size == 1000
    assert request.chunk_overlap == 200


@pytest.mark.parametrize(
    (
        "chunk_size",
        "chunk_overlap",
    ),
    [
        (0, 0),
        (100, -1),
        (100, 100),
        (100, 101),
    ],
)
def test_request_rejects_invalid_chunk_settings(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    with pytest.raises(ValidationError):
        PublicGuidelineIndexRequest(
            job_id="index-job-1",
            manifest_path="manifest.json",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def test_request_rejects_wrong_job_type() -> None:
    with pytest.raises(ValidationError):
        PublicGuidelineIndexRequest(
            job_id="index-job-1",
            job_type="CHAT",
            manifest_path="manifest.json",
        )


def test_request_rejects_non_json_manifest() -> None:
    with pytest.raises(
        ValidationError,
        match="JSON",
    ):
        PublicGuidelineIndexRequest(
            job_id="index-job-1",
            manifest_path="manifest.csv",
        )
