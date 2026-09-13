from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import scripts.purge_legacy_ocr_images as cleanup
from scripts.purge_legacy_ocr_images import (
    LegacyOcrPurgeError,
    build_purge_plan,
    execute_purge,
    format_plan,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
IMAGE_ID = "a" * 32
OTHER_IMAGE_ID = "b" * 32


def write_file(path: Path, *, size: int = 5, age_minutes: int = 61) -> Path:
    path.write_bytes(b"x" * size)
    timestamp = (NOW - timedelta(minutes=age_minutes)).timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def manifest(key: str, *, status: str, expires_at: datetime | None = None) -> dict[str, object]:
    return {
        "status": status,
        "expiresAt": expires_at.isoformat() if expires_at else None,
        "inputManifest": {"storageKey": key},
    }


def test_plan_only_selects_terminal_or_stale_unreferenced_uuid_legacy_files(tmp_path: Path) -> None:
    terminal = write_file(tmp_path / f"{IMAGE_ID}.jpg", size=7, age_minutes=1)
    old_orphan = write_file(tmp_path / f"{OTHER_IMAGE_ID}.processed.jpg", size=11)
    fresh_orphan = write_file(tmp_path / ("c" * 32 + ".png"), age_minutes=59)
    unrecognized = write_file(tmp_path / "user-upload.jpg")
    stale_temp = write_file(tmp_path / ("d" * 32 + ".jpg.tmp"), size=3)

    plan = build_purge_plan(
        tmp_path,
        [manifest(terminal.name, status="COMPLETE")],
        now=NOW,
    )

    assert {candidate.path for candidate in plan.eligible} == {terminal, old_orphan, stale_temp}
    assert plan.eligible_bytes == 21
    assert fresh_orphan.exists()
    assert unrecognized.exists()


def test_plan_protects_active_legacy_manifest_and_apply_refuses_while_it_exists(tmp_path: Path) -> None:
    active = write_file(tmp_path / f"{IMAGE_ID}.png")
    terminal = write_file(tmp_path / f"{OTHER_IMAGE_ID}.jpg")
    jobs = [
        manifest(active.name, status="QUEUED"),
        manifest(terminal.name, status="COMPLETE"),
    ]
    plan = build_purge_plan(tmp_path, jobs, now=NOW)

    assert plan.active_legacy_jobs == 1
    assert {candidate.path for candidate in plan.eligible} == {terminal}
    with pytest.raises(LegacyOcrPurgeError, match="active"):
        execute_purge(plan)
    assert active.exists()
    assert terminal.exists()


def test_expired_ready_manifest_is_eligible_but_unexpired_ready_is_protected(tmp_path: Path) -> None:
    expired = write_file(tmp_path / f"{IMAGE_ID}.jpg", age_minutes=1)
    active = write_file(tmp_path / f"{OTHER_IMAGE_ID}.jpg")

    plan = build_purge_plan(
        tmp_path,
        [
            manifest(expired.name, status="READY_FOR_REVIEW", expires_at=NOW - timedelta(seconds=1)),
            manifest(active.name, status="READY_FOR_REVIEW", expires_at=NOW + timedelta(seconds=1)),
        ],
        now=NOW,
    )

    assert {candidate.path for candidate in plan.eligible} == {expired}
    assert plan.active_legacy_jobs == 1


def test_unknown_manifest_status_is_fail_closed_and_protects_the_legacy_file(tmp_path: Path) -> None:
    unknown = write_file(tmp_path / f"{IMAGE_ID}.jpg")

    plan = build_purge_plan(tmp_path, [manifest(unknown.name, status="NEW_STATUS")], now=NOW)

    assert plan.active_legacy_jobs == 1
    assert not plan.eligible


def test_terminal_manifest_does_not_bypass_the_minimum_age_for_atomic_temp_files(tmp_path: Path) -> None:
    temp = write_file(tmp_path / f"{IMAGE_ID}.jpg.tmp", age_minutes=1)

    plan = build_purge_plan(tmp_path, [manifest(f"{IMAGE_ID}.jpg", status="COMPLETE")], now=NOW)

    assert not plan.eligible
    assert plan.protected_files == 1
    assert temp.exists()


def test_apply_deletes_only_validated_candidates_and_summary_never_prints_filenames(tmp_path: Path) -> None:
    eligible = write_file(tmp_path / f"{IMAGE_ID}.processed.jpg", size=9)
    untouched = write_file(tmp_path / "patient-prescription.png", size=13)
    plan = build_purge_plan(tmp_path, [], now=NOW)

    deleted = execute_purge(plan)
    summary = format_plan(plan, mode="apply", deleted=deleted)

    assert deleted == 1
    assert not eligible.exists()
    assert untouched.exists()
    assert json.loads(summary) == {
        "activeLegacyJobs": 0,
        "candidateBytes": 9,
        "candidateFiles": 1,
        "deletedFiles": 1,
        "mode": "apply",
        "protectedFiles": 0,
        "scannedFiles": 2,
    }
    assert eligible.name not in summary
    assert untouched.name not in summary


def test_rejects_symlink_root_and_skips_symlink_file(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    write_file(target / f"{IMAGE_ID}.jpg")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")

    with pytest.raises(LegacyOcrPurgeError, match="safe OCR temporary directory"):
        build_purge_plan(link, [], now=NOW)

    external = tmp_path / "external.jpg"
    write_file(external)
    candidate_link = target / f"{OTHER_IMAGE_ID}.jpg"
    candidate_link.symlink_to(external)
    plan = build_purge_plan(target, [], now=NOW)
    assert plan.scanned_files == 1
    assert {candidate.path.name for candidate in plan.eligible} == {f"{IMAGE_ID}.jpg"}


def test_main_does_not_expose_unexpected_error_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failed_run(_: object) -> int:
        raise RuntimeError("database password at C:/sensitive-path")

    monkeypatch.setattr(cleanup, "parse_args", lambda: object())
    monkeypatch.setattr(cleanup, "_run", failed_run)

    assert cleanup.main() == 1
    error_output = capsys.readouterr().err
    assert "RuntimeError" in error_output
    assert "password" not in error_output
    assert "sensitive-path" not in error_output
