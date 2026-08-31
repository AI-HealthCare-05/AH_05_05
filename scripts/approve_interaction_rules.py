from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.enums import InteractionReviewStatus  # noqa: E402
from app.models.interactions import (  # noqa: E402
    InteractionRule,
    InteractionRuleSource,
)
from scripts.import_interaction_staging import (  # noqa: E402
    InteractionStagingDataset,
    load_staging_dataset,
)


class InteractionApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class InteractionApprovalResult:
    dataset_version: str
    generation_id: str
    candidate_sha256: str
    candidate_count: int
    approved_count: int
    newly_approved_count: int
    reviewer: str
    approved_at: datetime


async def approve_staging_dataset(
    dataset: InteractionStagingDataset,
    *,
    expected_generation_id: str,
    expected_candidate_sha256: str,
    reviewer: str,
    approved_at: datetime | None = None,
) -> InteractionApprovalResult:
    normalized_reviewer = reviewer.strip()
    if not normalized_reviewer:
        raise InteractionApprovalError("승인자 식별자가 필요합니다.")
    if dataset.generation_id != expected_generation_id.strip():
        raise InteractionApprovalError("승인 대상 generation_id가 current staging 세대와 일치하지 않습니다.")
    if dataset.candidate_sha256 != expected_candidate_sha256.strip().lower():
        raise InteractionApprovalError("승인 대상 후보 파일의 SHA-256이 일치하지 않습니다.")

    approval_time = approved_at or datetime.now()
    expected_pair_keys = {candidate.pair_key for candidate in dataset.candidates}
    expected_source_keys = {
        (
            candidate.pair_key,
            source.source_id,
            source.document_id,
            source.record_id,
        )
        for candidate in dataset.candidates
        for source in candidate.source_records
    }

    async with in_transaction() as connection:
        rules = await InteractionRule.filter(
            rule_dataset_version=dataset.dataset_version,
        ).using_db(connection)
        if len(rules) != len(dataset.candidates):
            raise InteractionApprovalError(
                "DB 규칙 건수가 승인 후보 건수와 일치하지 않습니다: "
                f"expected={len(dataset.candidates)}, actual={len(rules)}"
            )
        rules_by_pair_key = {rule.pair_key: rule for rule in rules}
        if set(rules_by_pair_key) != expected_pair_keys:
            raise InteractionApprovalError("DB 규칙 pair_key 집합이 승인 후보와 일치하지 않습니다.")
        invalid_statuses = {
            rule.review_status
            for rule in rules
            if rule.review_status
            not in {
                InteractionReviewStatus.PENDING,
                InteractionReviewStatus.APPROVED,
            }
        }
        if invalid_statuses:
            raise InteractionApprovalError("PENDING 또는 APPROVED가 아닌 규칙이 포함되어 있습니다.")

        rule_ids = [rule.id for rule in rules]
        sources = await InteractionRuleSource.filter(
            interaction_rule_id__in=rule_ids,
        ).using_db(connection)
        pair_key_by_rule_id = {rule.id: rule.pair_key for rule in rules}
        stored_source_keys = {
            (
                pair_key_by_rule_id[source.interaction_rule_id],
                source.source_id,
                source.document_id,
                source.record_id,
            )
            for source in sources
        }
        if stored_source_keys != expected_source_keys:
            raise InteractionApprovalError("DB 출처 레코드가 승인 후보 출처와 일치하지 않습니다.")

        pending_ids = [rule.id for rule in rules if rule.review_status == InteractionReviewStatus.PENDING]
        if pending_ids:
            await (
                InteractionRule.filter(id__in=pending_ids)
                .using_db(connection)
                .update(
                    review_status=InteractionReviewStatus.APPROVED,
                    approved_at=approval_time,
                    updated_at=approval_time,
                )
            )
        approved_count = (
            await InteractionRule.filter(
                id__in=rule_ids,
                review_status=InteractionReviewStatus.APPROVED,
            )
            .using_db(connection)
            .count()
        )
        if approved_count != len(dataset.candidates):
            raise InteractionApprovalError("승인 후 APPROVED 규칙 건수가 후보 건수와 일치하지 않습니다.")
        approved_times = (
            await InteractionRule.filter(
                id__in=rule_ids,
            )
            .using_db(connection)
            .values_list(
                "approved_at",
                flat=True,
            )
        )
        effective_approved_at = max(value for value in approved_times if value is not None)

    return InteractionApprovalResult(
        dataset_version=dataset.dataset_version,
        generation_id=dataset.generation_id,
        candidate_sha256=dataset.candidate_sha256,
        candidate_count=len(dataset.candidates),
        approved_count=approved_count,
        newly_approved_count=len(pending_ids),
        reviewer=normalized_reviewer,
        approved_at=effective_approved_at,
    )


def write_approval_audit(
    *,
    dataset: InteractionStagingDataset,
    result: InteractionApprovalResult,
    reason: str,
) -> Path:
    if dataset.candidates_path is None:
        raise InteractionApprovalError("승인 감사 파일을 저장할 staging 후보 경로가 없습니다.")
    audit_path = dataset.candidates_path.parent / "interaction-approval-audit.json"
    temporary_path = audit_path.with_suffix(".json.tmp")
    payload = {
        **asdict(result),
        "approved_at": result.approved_at.isoformat(),
        "reason": reason.strip(),
    }
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(audit_path)
    return audit_path


async def _run_approval(
    *,
    marker_path: Path,
    expected_generation_id: str,
    expected_candidate_sha256: str,
    reviewer: str,
    reason: str,
) -> tuple[InteractionApprovalResult, Path]:
    dataset = load_staging_dataset(
        marker_path=marker_path,
        allow_pending=True,
    )
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await approve_staging_dataset(
            dataset,
            expected_generation_id=expected_generation_id,
            expected_candidate_sha256=expected_candidate_sha256,
            reviewer=reviewer,
        )
    finally:
        await Tortoise.close_connections()
    audit_path = write_approval_audit(
        dataset=dataset,
        result=result,
        reason=reason,
    )
    return result, audit_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("검증된 staging 세대와 로컬 DB가 정확히 일치할 때만 상호작용 규칙을 APPROVED로 승인합니다.")
    )
    parser.add_argument(
        "--marker",
        type=Path,
        default=(
            PROJECT_ROOT / "data" / "knowledge" / "processed" / "staging" / "interaction-pilot-v1" / "current.json"
        ),
    )
    parser.add_argument("--expected-generation-id", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--reason",
        default="MFDS DUR 병용금기 구조화 후보 로컬 검증 승인",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="실제 PENDING → APPROVED 변경에 대한 명시적 동의",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if not args.approve:
        print("실제 승인에는 --approve가 필요합니다.", file=sys.stderr)
        return 1
    try:
        result, audit_path = asyncio.run(
            _run_approval(
                marker_path=args.marker,
                expected_generation_id=args.expected_generation_id,
                expected_candidate_sha256=(args.expected_candidate_sha256),
                reviewer=args.reviewer,
                reason=args.reason,
            )
        )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    payload = {
        **asdict(result),
        "approved_at": result.approved_at.isoformat(),
        "audit_path": str(audit_path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
