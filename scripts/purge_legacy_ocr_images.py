"""Safely inventory or purge only legacy disk-backed OCR image artifacts.

The live OCR path uses volatile Redis keys and must never be addressed here.
This script does not modify OCR database rows or Redis keys.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import stat
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_LEGACY_IMAGE_NAME = re.compile(r"^[0-9a-f]{32}(?:\.processed)?\.(?:jpg|jpeg|png)$", re.IGNORECASE)
_ACTIVE_STATUSES = {"QUEUED", "PROCESSING"}
_READY_STATUS = "READY_FOR_REVIEW"
_TERMINAL_STATUSES = {"COMPLETE", "FAILED", "CANCELLED"}
_REPARSE_POINT = 0x0400


class LegacyOcrPurgeError(ValueError):
    """Raised before any deletion when a legacy-disk cleanup safety check fails."""


@dataclass(frozen=True)
class LegacyFileCandidate:
    path: Path
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class LegacyPurgePlan:
    root: Path
    eligible: tuple[LegacyFileCandidate, ...]
    scanned_files: int
    protected_files: int
    active_legacy_jobs: int

    @property
    def eligible_bytes(self) -> int:
        return sum(candidate.size for candidate in self.eligible)


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    return bool(getattr(file_stat, "st_file_attributes", 0) & _REPARSE_POINT)


def _safe_root(root: Path) -> Path:
    try:
        root_stat = os.lstat(root)
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise LegacyOcrPurgeError("safe OCR temporary directory is unavailable") from error
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode) or _is_reparse_point(root_stat):
        raise LegacyOcrPurgeError("safe OCR temporary directory is required")
    return resolved


def _is_legacy_filename(name: str) -> bool:
    return bool(_LEGACY_IMAGE_NAME.fullmatch(name))


def _is_stale_temp_name(name: str) -> bool:
    return name.endswith(".tmp") and _is_legacy_filename(name.removesuffix(".tmp"))


def _safe_legacy_key(value: object) -> str | None:
    if not isinstance(value, str) or value.startswith("ocr-image:"):
        return None
    candidate = Path(value)
    if candidate.name != value or not _is_legacy_filename(value):
        return None
    return value


def _manifest_from_job(job: Mapping[str, object]) -> Mapping[str, object]:
    manifest = job.get("inputManifest", job.get("input_manifest"))
    return manifest if isinstance(manifest, Mapping) else {}


def _job_legacy_keys(job: Mapping[str, object]) -> set[str]:
    manifest = _manifest_from_job(job)
    return {
        key
        for field in ("storageKey", "processedStorageKey")
        if (key := _safe_legacy_key(manifest.get(field))) is not None
    }


def _job_is_active(job: Mapping[str, object], *, now: datetime) -> bool:
    status = str(job.get("status", ""))
    if status in _ACTIVE_STATUSES:
        return True
    if status in _TERMINAL_STATUSES:
        return False
    if status != _READY_STATUS:
        return True
    raw_expiry = job.get("expiresAt", job.get("expires_at"))
    if raw_expiry is None:
        return True
    if isinstance(raw_expiry, str):
        try:
            raw_expiry = datetime.fromisoformat(raw_expiry)
        except ValueError:
            return True
    if not isinstance(raw_expiry, datetime):
        return True
    expiry = raw_expiry if raw_expiry.tzinfo else raw_expiry.replace(tzinfo=UTC)
    return expiry > now


def _candidate_stat(path: Path) -> os.stat_result | None:
    try:
        file_stat = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode) or _is_reparse_point(file_stat):
        return None
    return file_stat


def build_purge_plan(
    root: Path,
    jobs: Iterable[Mapping[str, object]],
    *,
    now: datetime | None = None,
    min_age: timedelta = timedelta(minutes=60),
) -> LegacyPurgePlan:
    """Build a non-mutating deletion plan without exposing filenames in output."""
    if min_age < timedelta(minutes=60):
        raise LegacyOcrPurgeError("minimum orphan age must be at least 60 minutes")
    safe_root = _safe_root(root)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    active_keys: set[str] = set()
    terminal_keys: set[str] = set()
    active_jobs = 0
    for job in jobs:
        keys = _job_legacy_keys(job)
        if not keys:
            continue
        if _job_is_active(job, now=current):
            active_jobs += 1
            active_keys.update(keys)
        else:
            terminal_keys.update(keys)

    eligible: list[LegacyFileCandidate] = []
    scanned_files = 0
    protected_files = 0
    for path in safe_root.iterdir():
        file_stat = _candidate_stat(path)
        if file_stat is None:
            continue
        scanned_files += 1
        name = path.name
        if not (_is_legacy_filename(name) or _is_stale_temp_name(name)):
            continue
        legacy_name = name.removesuffix(".tmp")
        modified_at = datetime.fromtimestamp(file_stat.st_mtime, tz=UTC)
        referenced_by_active_job = legacy_name in active_keys
        terminal_or_expired_reference = legacy_name in terminal_keys
        old_enough = current - modified_at >= min_age
        eligible_by_reference_or_age = (
            old_enough if _is_stale_temp_name(name) else terminal_or_expired_reference or old_enough
        )
        if referenced_by_active_job or not eligible_by_reference_or_age:
            protected_files += 1
            continue
        eligible.append(
            LegacyFileCandidate(
                path=path,
                device=file_stat.st_dev,
                inode=file_stat.st_ino,
                size=file_stat.st_size,
                mtime_ns=file_stat.st_mtime_ns,
            )
        )
    return LegacyPurgePlan(
        root=safe_root,
        eligible=tuple(eligible),
        scanned_files=scanned_files,
        protected_files=protected_files,
        active_legacy_jobs=active_jobs,
    )


def _validate_unchanged_candidate(plan: LegacyPurgePlan, candidate: LegacyFileCandidate) -> None:
    if candidate.path.parent != plan.root:
        raise LegacyOcrPurgeError("candidate escaped the configured OCR temporary directory")
    file_stat = _candidate_stat(candidate.path)
    if file_stat is None:
        raise LegacyOcrPurgeError("candidate changed; rebuild the dry-run plan")
    if (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    ) != (
        candidate.device,
        candidate.inode,
        candidate.size,
        candidate.mtime_ns,
    ):
        raise LegacyOcrPurgeError("candidate changed; rebuild the dry-run plan")


def execute_purge(plan: LegacyPurgePlan) -> int:
    """Delete a preflighted plan; callers must take the maintenance window first."""
    if plan.active_legacy_jobs:
        raise LegacyOcrPurgeError("active legacy OCR jobs exist; refusing deletion")
    _safe_root(plan.root)
    for candidate in plan.eligible:
        _validate_unchanged_candidate(plan, candidate)
    for candidate in plan.eligible:
        candidate.path.unlink()
    return len(plan.eligible)


def format_plan(plan: LegacyPurgePlan, *, mode: str, deleted: int = 0) -> str:
    """Return aggregate-only JSON; never expose sensitive filename or image contents."""
    return json.dumps(
        {
            "activeLegacyJobs": plan.active_legacy_jobs,
            "candidateBytes": plan.eligible_bytes,
            "candidateFiles": len(plan.eligible),
            "deletedFiles": deleted,
            "mode": mode,
            "protectedFiles": plan.protected_files,
            "scannedFiles": plan.scanned_files,
        },
        sort_keys=True,
    )


async def _load_job_snapshot() -> list[dict[str, object]]:
    from tortoise import Tortoise

    from app.core.db.databases import TORTOISE_ORM
    from app.models.ocr import OcrJob

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await OcrJob.all().values("status", "expires_at", "input_manifest")
    finally:
        await Tortoise.close_connections()


def _configured_root(argument_root: Path | None) -> Path:
    if argument_root is not None:
        return argument_root if argument_root.is_absolute() else PROJECT_ROOT / argument_root
    from app.core.config import config

    root = config.OCR_TEMP_DIR
    return root if root.is_absolute() else PROJECT_ROOT / root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory or purge only validated legacy OCR disk artifacts.")
    parser.add_argument("--root", type=Path, help="explicit OCR_TEMP_DIR override; no recursive scan")
    parser.add_argument("--min-age-minutes", type=int, default=60)
    parser.add_argument("--apply", action="store_true", help="perform deletion after all safety gates pass")
    parser.add_argument(
        "--maintenance-window",
        action="store_true",
        help="attest that API and OCR workers are stopped for the deletion window",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    min_age = timedelta(minutes=args.min_age_minutes)
    root = _configured_root(args.root)
    jobs = await _load_job_snapshot()
    plan = build_purge_plan(root, jobs, min_age=min_age)
    if not args.apply:
        print(format_plan(plan, mode="dry-run"))
        return 0
    if not args.maintenance_window:
        raise LegacyOcrPurgeError("--apply requires an active maintenance window")

    # Read a fresh DB snapshot immediately before deletion. The operational maintenance
    # window prevents a newly queued legacy job from racing this snapshot.
    fresh_plan = build_purge_plan(root, await _load_job_snapshot(), min_age=min_age)
    deleted = execute_purge(fresh_plan)
    print(format_plan(fresh_plan, mode="apply", deleted=deleted))
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(_run(args))
    except LegacyOcrPurgeError as error:
        print(f"legacy OCR cleanup refused: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"legacy OCR cleanup refused: unexpected {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
