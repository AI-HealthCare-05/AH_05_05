from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_worker.services.medication_safety_approval_service import (  # noqa: E402
    build_approval_report,
)
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.enums import InteractionReviewStatus  # noqa: E402
from app.models.interactions import MedicationSafetyRule  # noqa: E402


class MedicationSafetyApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class MedicationSafetyApprovalResult:
    dataset_version: str
    reviewer: str
    rule_count: int
    valid_count: int
    invalid_count: int
    issue_counts: dict[str, int]
    approved_count: int
    newly_approved_count: int
    approved_rule_key_sha256: str
    applied: bool
    approved_at: datetime | None


def _digest_rule_keys(rule_keys: Sequence[str]) -> str:
    encoded = "\n".join(sorted(rule_keys)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def approve_dataset(
    *,
    dataset_version: str,
    reviewer: str,
    expected_count: int,
    apply: bool,
    approved_at: datetime | None = None,
) -> MedicationSafetyApprovalResult:
    normalized_version = dataset_version.strip()
    normalized_reviewer = reviewer.strip()
    if not normalized_version:
        raise MedicationSafetyApprovalError("데이터셋 버전이 필요합니다.")
    if not normalized_reviewer:
        raise MedicationSafetyApprovalError("승인자 식별자가 필요합니다.")
    if expected_count <= 0:
        raise MedicationSafetyApprovalError("예상 규칙 건수는 양수여야 합니다.")

    approval_time = approved_at or datetime.now()
    async with in_transaction() as connection:
        rules = await (
            MedicationSafetyRule.filter(rule_dataset_version=normalized_version)
            .using_db(connection)
            .prefetch_related("conditions", "sources")
            .order_by("rule_key")
        )
        if len(rules) != expected_count:
            raise MedicationSafetyApprovalError(
                f"DB 규칙 건수가 예상 건수와 일치하지 않습니다: expected={expected_count}, actual={len(rules)}"
            )

        report, issues = build_approval_report(
            [(rule, rule.conditions, rule.sources) for rule in rules],
            dataset_version=normalized_version,
        )
        if report.invalid_count:
            sample = ", ".join(f"{issue.rule_key}:{issue.code}" for issue in issues[:5])
            raise MedicationSafetyApprovalError(
                f"승인 전 규칙 검증에 실패했습니다: invalid={report.invalid_count}, sample={sample}"
            )
        if report.valid_count != expected_count:
            raise MedicationSafetyApprovalError(
                "유효 규칙 건수가 예상 건수와 일치하지 않습니다: "
                f"expected={expected_count}, actual={report.valid_count}"
            )

        pending_ids = [rule.id for rule in rules if rule.review_status == InteractionReviewStatus.PENDING]
        if apply and pending_ids:
            await (
                MedicationSafetyRule.filter(id__in=pending_ids)
                .using_db(connection)
                .update(
                    review_status=InteractionReviewStatus.APPROVED,
                    approved_at=approval_time,
                    updated_at=approval_time,
                )
            )

        approved_count = sum(rule.review_status == InteractionReviewStatus.APPROVED for rule in rules)
        if apply:
            approved_count += len(pending_ids)
            if approved_count != expected_count:
                raise MedicationSafetyApprovalError("승인 후 APPROVED 규칙 건수 검증에 실패했습니다.")
            approved_times = await (
                MedicationSafetyRule.filter(id__in=[rule.id for rule in rules])
                .using_db(connection)
                .values_list("approved_at", flat=True)
            )
            effective_approved_at = max(value for value in approved_times if value is not None)
        else:
            effective_approved_at = None

    return MedicationSafetyApprovalResult(
        dataset_version=normalized_version,
        reviewer=normalized_reviewer,
        rule_count=report.rule_count,
        valid_count=report.valid_count,
        invalid_count=report.invalid_count,
        issue_counts=report.issue_counts,
        approved_count=approved_count,
        newly_approved_count=len(pending_ids) if apply else 0,
        approved_rule_key_sha256=_digest_rule_keys([rule.rule_key for rule in rules]),
        applied=apply,
        approved_at=effective_approved_at,
    )


def write_approval_audit(result: MedicationSafetyApprovalResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = asdict(result)
    payload["approved_at"] = result.approved_at.isoformat() if result.approved_at else None
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


async def _run(args: argparse.Namespace) -> MedicationSafetyApprovalResult:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await approve_dataset(
            dataset_version=args.dataset_version,
            reviewer=args.reviewer,
            expected_count=args.expected_count,
            apply=args.apply,
        )
    finally:
        await Tortoise.close_connections()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="의약품 안전 규칙 데이터셋을 전수 검증하고 명시적 --apply에서만 승인합니다."
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--audit-path",
        type=Path,
        default=PROJECT_ROOT / "output" / "medication-safety-approval-audit.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = asyncio.run(_run(args))
        audit_path = write_approval_audit(result, args.audit_path) if args.apply else None
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    payload = asdict(result)
    payload["approved_at"] = result.approved_at.isoformat() if result.approved_at else None
    payload["audit_path"] = str(audit_path) if audit_path else None
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
