from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.benchmark_ocr_preprocess_v32 import generate_preprocessed_artifact


def test_generate_only_writes_anonymous_preprocessed_artifact(tmp_path: Path) -> None:
    def preprocess(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            template_image=SimpleNamespace(jpeg_bytes=b"jpeg", width=1200, height=800),
            quality_state=SimpleNamespace(value="PROCESSED"),
            preprocessing_mode=SimpleNamespace(value="PERSPECTIVE"),
            reasons=("perspective_rectified",),
            operations=("output_unsharp_mild",),
        )

    payload = generate_preprocessed_artifact(
        b"private-source",
        "image/jpeg",
        artifact_dir=tmp_path,
        preprocess_version="v3.2.2",
        preprocess=preprocess,
    )

    assert (tmp_path / "preprocessed.jpg").read_bytes() == b"jpeg"
    assert payload["preprocessVersion"] == "v3.2.2"
    assert payload["providerJpegBytes"] == 4
    assert payload["privacy"]["sourcePersisted"] is False
    assert "private-source" not in json.dumps(payload)
