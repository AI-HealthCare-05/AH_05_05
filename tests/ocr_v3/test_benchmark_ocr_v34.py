from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from scripts import benchmark_ocr_v34 as subject


def _jpeg_bytes() -> bytes:
    return _image_bytes("JPEG")


def _png_bytes() -> bytes:
    return _image_bytes("PNG")


def _image_bytes(image_format: str) -> bytes:
    image = Image.new("RGB", (32, 24), color=(180, 200, 220))
    import io

    output = io.BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_checkpoint_rejects_corrupt_envelope(tmp_path: Path) -> None:
    identity = {"run": "fixed"}
    entry = {"id": "sample-01", "sha256": "a" * 64}
    path = tmp_path / "sample-01-v3.4.1-identity.json"
    subject.write_checkpoint(path, {"id": "sample-01", "identity": subject.digest(identity)})
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["checksum"] = "0" * 64
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupt checkpoint"):
        subject.load_checkpoint(path, identity=identity, entry=entry, version="v3.4.1", variant="identity")


def test_checkpoint_rejects_stale_identity_instead_of_skipping(tmp_path: Path) -> None:
    identity = {"run": "new"}
    entry = {"id": "sample-01", "sha256": "a" * 64}
    path = tmp_path / "sample-01-v3.4.1-identity.json"
    subject.write_checkpoint(
        path,
        {
            "id": "sample-01",
            "sha256": entry["sha256"],
            "version": "v3.4.1",
            "variant": "identity",
            "identity": subject.digest({"run": "old"}),
        },
    )

    with pytest.raises(ValueError, match="Stale checkpoint"):
        subject.load_checkpoint(path, identity=identity, entry=entry, version="v3.4.1", variant="identity")


def test_inflight_marker_uses_exclusive_creation_even_when_a_racy_exists_check_lies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "sample-01-v3.4.3-identity.json"
    marker = checkpoint.with_suffix(".inflight")
    original_exists = Path.exists

    def racy_exists(path: Path) -> bool:
        return False if path == marker else original_exists(path)

    monkeypatch.setattr(Path, "exists", racy_exists)
    subject._write_inflight(checkpoint, identity={"attempt": 1})

    with pytest.raises(RuntimeError, match="Unfinished OCR attempt"):
        subject._write_inflight(checkpoint, identity={"attempt": 2})


def test_checkpoint_rejects_cached_result_for_a_different_transformed_input(tmp_path: Path) -> None:
    identity = {"run": "fixed"}
    entry = {"id": "sample-01", "sha256": "a" * 64}
    transform = {"sourceSha256": "a" * 64, "transformedSha256": "b" * 64, "parameters": {"name": "blur"}}
    path = tmp_path / "sample-01-v3.4.3-blur.json"
    subject.write_checkpoint(
        path,
        {
            "id": entry["id"],
            "sha256": entry["sha256"],
            "version": "v3.4.3",
            "variant": "blur",
            "identity": subject.digest(identity),
            "transform": transform,
        },
    )

    with pytest.raises(ValueError, match="Stale checkpoint"):
        subject.load_checkpoint(
            path,
            identity=identity,
            entry=entry,
            version="v3.4.3",
            variant="blur",
            transform={**transform, "transformedSha256": "c" * 64},
        )


def test_version_registry_rejects_empty_duplicate_and_unknown_versions() -> None:
    with pytest.raises(ValueError, match="empty"):
        subject.validate_versions(())
    with pytest.raises(ValueError, match="duplicates"):
        subject.validate_versions(("v3.1.3", "v3.1.3"))
    with pytest.raises(ValueError, match="Unsupported OCR preprocess version"):
        subject.validate_versions(("not-a-profile",))


def test_default_comparison_contains_all_baselines_and_best_candidate() -> None:
    assert subject.DEFAULT_VERSIONS == ("v3.1.3", "v3.2.7", "v3.3.1", "v3.4.1")


def test_result_whitelist_excludes_unapproved_review_and_ocr_data() -> None:
    analysis = SimpleNamespace(
        project_review={
            "medications": [
                {
                    "name": "allowed",
                    "strength": "allowed",
                    "doseQuantity": "allowed",
                    "timesPerDay": "allowed",
                    "days": "allowed",
                    "evidence": "must-not-persist",
                    "patientName": "must-not-persist",
                }
            ],
            "patient": {"name": "must-not-persist"},
        },
        requires_recapture=False,
        recapture_reasons=("safe_reason",),
        stages=[{"name": "preprocess", "status": "succeeded", "elapsedMs": 12, "callCount": 0, "secret": "no"}],
    )

    result = subject.safe_analysis_result(analysis, preprocess_metadata={"operations": ["safe"]})

    assert result["review"] == {
        "medications": [
            {
                "name": "allowed",
                "strength": "allowed",
                "doseQuantity": "allowed",
                "timesPerDay": "allowed",
                "days": "allowed",
            }
        ]
    }
    assert result["stages"] == [{"name": "preprocess", "status": "succeeded", "elapsedMs": 12, "callCount": 0}]
    rendered = json.dumps(result)
    assert "must-not-persist" not in rendered
    assert "patient" not in rendered
    assert "secret" not in rendered


@pytest.mark.parametrize("variant", ("identity", "rotate", "perspective", "shadow", "blur", "downscale"))
def test_variants_are_deterministic_and_keep_only_hashes_and_parameters(variant: str) -> None:
    source = _jpeg_bytes()

    first = subject.make_variant(source, variant)
    second = subject.make_variant(source, variant)

    assert first.source_sha256 == second.source_sha256
    assert first.transformed_sha256 == second.transformed_sha256
    assert first.parameters == second.parameters
    assert first.content == second.content
    assert "content" not in first.as_manifest()


def test_identity_variant_preserves_png_mime_for_native_preprocessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _png_bytes()
    entry = {"id": "sample-01", "file": "sample.png", "sha256": subject.hashlib.sha256(source).hexdigest()}
    monkeypatch.setattr(subject, "SOURCE", tmp_path)
    (tmp_path / "sample.png").write_bytes(source)

    _variant, image = subject._variant_image(entry, "identity")

    assert image.media_type == "image/png"
    assert image.provider_format == "png"


@pytest.mark.asyncio
async def test_completed_run_resumes_without_initializing_or_calling_provider(tmp_path, monkeypatch):
    source = _png_bytes()
    entry = {"id": "sample-01", "file": "sample.png", "sha256": subject.hashlib.sha256(source).hexdigest()}
    (tmp_path / "sample.png").write_bytes(source)
    monkeypatch.setattr(subject, "SOURCE", tmp_path)
    identity = {"images": [entry], "versions": ["v3.4.1"], "config": {"variants": ["identity"]}}
    transformed, _ = subject._variant_image(entry, "identity")
    result = {
        "id": entry["id"],
        "sha256": entry["sha256"],
        "version": "v3.4.1",
        "variant": "identity",
        "identity": subject.digest(identity),
        "transform": transformed.as_manifest(),
        "review": {"medications": []},
        "providerCallCount": 1,
    }
    subject.write_checkpoint(subject._checkpoint_path(tmp_path, entry, "v3.4.1", "identity"), result)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Completed work must not invoke native analysis")

    monkeypatch.setattr(subject, "_native_analysis", forbidden)
    assert await subject.run(identity, tmp_path) == [result]


@pytest.mark.asyncio
async def test_interrupted_run_preserves_completed_unit_and_blocks_unknown_call_replay(tmp_path, monkeypatch):
    source = _png_bytes()
    entries = [
        {"id": f"sample-{index:02d}", "file": "sample.png", "sha256": subject.hashlib.sha256(source).hexdigest()}
        for index in (1, 2)
    ]
    (tmp_path / "sample.png").write_bytes(source)
    monkeypatch.setattr(subject, "SOURCE", tmp_path)
    identity = {"images": entries, "versions": ["v3.4.1"], "config": {"variants": ["identity"]}}
    calls = []

    async def interrupted(image, *, version, checkpoint, identity):
        calls.append(checkpoint.name)
        subject._write_inflight(checkpoint, identity=identity)
        if len(calls) == 2:
            raise RuntimeError("simulated interruption after provider start")
        return SimpleNamespace(project_review={"medications": []}), {}, 1

    monkeypatch.setattr(subject, "_native_analysis", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        await subject.run(identity, tmp_path)
    first = subject._checkpoint_path(tmp_path, entries[0], "v3.4.1", "identity")
    completed = first.read_bytes()
    with pytest.raises(RuntimeError, match="Unfinished OCR attempt"):
        await subject.run(identity, tmp_path)
    assert first.read_bytes() == completed
    assert len(calls) == 2
