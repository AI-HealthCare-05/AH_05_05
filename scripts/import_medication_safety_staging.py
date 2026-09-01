from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_worker.schemas.medication_safety import (  # noqa: E402
    MedicationSafetyConditionCandidate,
    MedicationSafetyRuleCandidate,
    MedicationSafetySourceRecord,
)
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.enums import (  # noqa: E402
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionReviewStatus,
    InteractionRiskLevel,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)
from app.models.interactions import (  # noqa: E402
    InteractionEntity,
    InteractionEntityIdentifier,
    MedicationSafetyRule,
    MedicationSafetyRuleCondition,
    MedicationSafetyRuleSource,
)


class MedicationSafetyStagingImportError(ValueError):
    pass


@dataclass(frozen=True)
class MedicationSafetyStagingDataset:
    dataset_version: str
    generation_id: str
    candidates: list[MedicationSafetyRuleCandidate]
    ready_for_rdb_import: bool
    candidate_sha256: str
    candidates_path: Path | None = None


@dataclass(frozen=True)
class MedicationSafetyImportResult:
    candidates: int
    entities_created: int
    identifiers_created: int
    rules_created: int
    conditions_created: int
    sources_created: int

    @property
    def total_created(self) -> int:
        return (
            self.entities_created
            + self.identifiers_created
            + self.rules_created
            + self.conditions_created
            + self.sources_created
        )


def load_medication_safety_staging_dataset(
    *,
    marker_path: Path,
    allow_pending: bool,
    processed_root: Path | None = None,
) -> MedicationSafetyStagingDataset:
    marker_path = marker_path.resolve()
    marker = _read_json_object(marker_path)
    root = processed_root.resolve() if processed_root is not None else marker_path.parents[2]
    dataset_version = _required_text(marker, "dataset_version")
    generation_id = _required_text(marker, "generation_id")
    expected_marker = (root / "staging" / dataset_version / "current.json").resolve()
    if marker_path != expected_marker:
        raise MedicationSafetyStagingImportError(
            "current marker는 processed/staging/<version>/current.json 경로에 있어야 합니다."
        )

    candidates_path = _resolve_managed_path(root, _required_text(marker, "candidates_path"))
    quality_path = _resolve_managed_path(root, _required_text(marker, "quality_report_path"))
    expected_sha = _required_text(marker, "candidate_sha256")
    actual_sha = _sha256_file(candidates_path)
    if actual_sha != expected_sha:
        raise MedicationSafetyStagingImportError("후보 파일의 SHA-256이 current marker와 일치하지 않습니다.")

    quality = _read_json_object(quality_path)
    for key, expected in {
        "dataset_version": dataset_version,
        "generation_id": generation_id,
        "candidate_sha256": expected_sha,
    }.items():
        if quality.get(key) != expected:
            raise MedicationSafetyStagingImportError(f"품질 보고서의 {key} 값이 current marker와 일치하지 않습니다.")
    quality_candidates_path = _resolve_managed_path(
        root,
        _required_text(quality, "candidates_path"),
    )
    if quality_candidates_path != candidates_path:
        raise MedicationSafetyStagingImportError("품질 보고서와 current marker의 후보 경로가 다릅니다.")

    ready = marker.get("ready_for_rdb_import") is True and quality.get("ready_for_rdb_import") is True
    if not ready and not allow_pending:
        raise MedicationSafetyStagingImportError("검수 대기 후보를 적재하려면 --allow-pending이 필요합니다.")
    candidates = _read_candidates(candidates_path)
    expected_count = marker.get("candidate_count")
    if expected_count != len(candidates) or quality.get("candidate_count") != len(candidates):
        raise MedicationSafetyStagingImportError("marker·품질 보고서·후보 파일의 건수가 일치하지 않습니다.")
    if any(candidate.dataset_version != dataset_version for candidate in candidates):
        raise MedicationSafetyStagingImportError("후보의 dataset_version이 current marker와 일치하지 않습니다.")
    if len({candidate.rule_key for candidate in candidates}) != len(candidates):
        raise MedicationSafetyStagingImportError("후보 파일에 중복 rule_key가 있습니다.")
    return MedicationSafetyStagingDataset(
        dataset_version=dataset_version,
        generation_id=generation_id,
        candidates=candidates,
        ready_for_rdb_import=ready,
        candidate_sha256=actual_sha,
        candidates_path=candidates_path,
    )


async def import_medication_safety_staging_dataset(
    dataset: MedicationSafetyStagingDataset,
) -> MedicationSafetyImportResult:
    _validate_dataset(dataset)
    async with in_transaction() as connection:
        result = await _upsert_candidates(dataset.candidates, connection=connection)
        await _verify_stored_dataset(dataset, connection=connection)
        return result


async def _upsert_candidates(
    candidates: list[MedicationSafetyRuleCandidate],
    *,
    connection: BaseDBAsyncClient,
) -> MedicationSafetyImportResult:
    entities_created = 0
    identifiers_created = 0
    rules_created = 0
    conditions_created = 0
    sources_created = 0

    for candidate in candidates:
        source_id = candidate.sources[0].source_id
        entity, entity_created, identifier_created = await _resolve_entity(
            candidate,
            source_id=source_id,
            connection=connection,
        )
        entities_created += int(entity_created)
        identifiers_created += int(identifier_created)

        rule, created = await MedicationSafetyRule.get_or_create(
            rule_key=candidate.rule_key,
            rule_dataset_version=candidate.dataset_version,
            defaults={
                "interaction_entity_id": entity.id,
                "rule_type": MedicationSafetyRuleType(candidate.rule_type.value),
                "risk_level": InteractionRiskLevel(candidate.risk_level.value),
                "guidance_text": candidate.guidance_text,
                "review_status": InteractionReviewStatus.PENDING,
                "extraction_method": InteractionExtractionMethod(candidate.extraction_method.value),
            },
            using_db=connection,
        )
        if created:
            rules_created += 1
        else:
            _assert_existing_rule_matches(rule, candidate, entity_id=entity.id)

        for condition in candidate.conditions:
            stored_condition, condition_created = await MedicationSafetyRuleCondition.get_or_create(
                medication_safety_rule_id=rule.id,
                condition_group_no=condition.condition_group_no,
                condition_order=condition.condition_order,
                defaults={
                    "condition_kind": SafetyConditionKind(condition.condition_kind.value),
                    "comparison_operator": SafetyComparisonOperator(condition.comparison_operator.value),
                    "value_min": condition.value_min,
                    "value_max": condition.value_max,
                    "value_text": condition.value_text,
                    "unit": condition.unit,
                },
                using_db=connection,
            )
            if condition_created:
                conditions_created += 1
            else:
                _assert_existing_condition_matches(stored_condition, condition)

        for source in candidate.sources:
            stored_source, source_created = await MedicationSafetyRuleSource.get_or_create(
                medication_safety_rule_id=rule.id,
                source_id=source.source_id,
                document_id=source.document_id,
                record_id=source.record_id,
                defaults={
                    "raw_effect_text": source.raw_effect_text,
                    "source_published_at": (
                        date.fromisoformat(source.source_published_at) if source.source_published_at else None
                    ),
                    "source_url": source.source_url,
                },
                using_db=connection,
            )
            if source_created:
                sources_created += 1
            else:
                _assert_existing_source_matches(stored_source, source)

    return MedicationSafetyImportResult(
        candidates=len(candidates),
        entities_created=entities_created,
        identifiers_created=identifiers_created,
        rules_created=rules_created,
        conditions_created=conditions_created,
        sources_created=sources_created,
    )


async def _resolve_entity(
    candidate: MedicationSafetyRuleCandidate,
    *,
    source_id: str,
    connection: BaseDBAsyncClient,
) -> tuple[InteractionEntity, bool, bool]:
    source_code = candidate.entity.source_code
    if source_code:
        identifier = (
            await InteractionEntityIdentifier.filter(
                source_id=source_id,
                source_code=source_code,
            )
            .using_db(connection)
            .first()
        )
        if identifier is not None:
            return await InteractionEntity.get(id=identifier.interaction_entity_id).using_db(connection), False, False

    entity, entity_created = await InteractionEntity.get_or_create(
        entity_kind=InteractionEntityKind(candidate.entity.kind.value),
        normalized_name=candidate.entity.normalized_name,
        defaults={"canonical_name": candidate.entity.display_name},
        using_db=connection,
    )
    identifier_created = False
    if source_code:
        _, identifier_created = await InteractionEntityIdentifier.get_or_create(
            source_id=source_id,
            source_code=source_code,
            defaults={"interaction_entity_id": entity.id},
            using_db=connection,
        )
    return entity, entity_created, identifier_created


async def _verify_stored_dataset(
    dataset: MedicationSafetyStagingDataset,
    *,
    connection: BaseDBAsyncClient,
) -> None:
    rules = await MedicationSafetyRule.filter(
        rule_dataset_version=dataset.dataset_version,
    ).using_db(connection)
    if len(rules) != len(dataset.candidates):
        raise RuntimeError(
            "안전 규칙 적재 건수가 후보 건수와 일치하지 않습니다: "
            f"expected={len(dataset.candidates)}, actual={len(rules)}"
        )
    rule_ids = [rule.id for rule in rules]
    expected_conditions = sum(len(candidate.conditions) for candidate in dataset.candidates)
    expected_sources = sum(len(candidate.sources) for candidate in dataset.candidates)
    actual_conditions = (
        await MedicationSafetyRuleCondition.filter(medication_safety_rule_id__in=rule_ids).using_db(connection).count()
    )
    actual_sources = (
        await MedicationSafetyRuleSource.filter(medication_safety_rule_id__in=rule_ids).using_db(connection).count()
    )
    if actual_conditions != expected_conditions or actual_sources != expected_sources:
        raise RuntimeError(
            "안전 규칙 하위 레코드 적재 건수가 후보와 일치하지 않습니다: "
            f"conditions={actual_conditions}/{expected_conditions}, sources={actual_sources}/{expected_sources}"
        )


def _assert_existing_rule_matches(
    rule: MedicationSafetyRule,
    candidate: MedicationSafetyRuleCandidate,
    *,
    entity_id: int,
) -> None:
    actual = (
        rule.interaction_entity_id,
        rule.rule_type.value,
        rule.risk_level.value,
        rule.guidance_text,
        rule.review_status.value,
        rule.extraction_method.value,
    )
    expected = (
        entity_id,
        candidate.rule_type.value,
        candidate.risk_level.value,
        candidate.guidance_text,
        InteractionReviewStatus.PENDING.value,
        candidate.extraction_method.value,
    )
    if actual != expected:
        raise MedicationSafetyStagingImportError("같은 버전의 기존 안전 규칙이 후보 내용과 다릅니다.")


def _assert_existing_condition_matches(
    stored: MedicationSafetyRuleCondition,
    candidate: MedicationSafetyConditionCandidate,
) -> None:
    actual_values = (
        stored.condition_kind.value,
        stored.comparison_operator.value,
        stored.value_min,
        stored.value_max,
        stored.value_text,
        stored.unit,
    )
    expected_values = (
        candidate.condition_kind.value,
        candidate.comparison_operator.value,
        candidate.value_min,
        candidate.value_max,
        candidate.value_text,
        candidate.unit,
    )
    if actual_values != expected_values:
        raise MedicationSafetyStagingImportError("기존 안전 규칙 조건이 후보 내용과 다릅니다.")


def _assert_existing_source_matches(
    stored: MedicationSafetyRuleSource,
    candidate: MedicationSafetySourceRecord,
) -> None:
    expected_date = date.fromisoformat(candidate.source_published_at) if candidate.source_published_at else None
    if (
        stored.raw_effect_text,
        stored.source_published_at,
        stored.source_url,
    ) != (
        candidate.raw_effect_text,
        expected_date,
        candidate.source_url,
    ):
        raise MedicationSafetyStagingImportError("기존 안전 규칙 출처가 후보 내용과 다릅니다.")


def _validate_dataset(dataset: MedicationSafetyStagingDataset) -> None:
    if any(candidate.dataset_version != dataset.dataset_version for candidate in dataset.candidates):
        raise MedicationSafetyStagingImportError("후보 dataset_version이 적재 dataset과 다릅니다.")
    if len({candidate.rule_key for candidate in dataset.candidates}) != len(dataset.candidates):
        raise MedicationSafetyStagingImportError("후보 dataset에 중복 rule_key가 있습니다.")


def _read_candidates(path: Path) -> list[MedicationSafetyRuleCandidate]:
    candidates: list[MedicationSafetyRuleCandidate] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                candidates.append(MedicationSafetyRuleCandidate.model_validate_json(line))
            except ValidationError as error:
                raise MedicationSafetyStagingImportError(
                    f"후보 JSONL {line_number}행이 유효하지 않습니다: {error.errors()[0]['msg']}"
                ) from error
    except OSError as error:
        raise MedicationSafetyStagingImportError(f"후보 파일을 읽을 수 없습니다: {path}") from error
    return candidates


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MedicationSafetyStagingImportError(f"JSON 파일을 읽을 수 없습니다: {path}") from error
    if not isinstance(payload, dict):
        raise MedicationSafetyStagingImportError(f"JSON 객체가 필요합니다: {path}")
    return payload


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MedicationSafetyStagingImportError(f"{key} 값이 필요합니다.")
    return value.strip()


def _resolve_managed_path(root: Path, value: str) -> Path:
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise MedicationSafetyStagingImportError("관리 디렉터리 밖의 경로는 사용할 수 없습니다.")
    return path


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise MedicationSafetyStagingImportError(f"후보 파일을 읽을 수 없습니다: {path}") from error


async def _run_import(
    *,
    marker_path: Path,
    allow_pending: bool,
    dry_run: bool,
) -> tuple[MedicationSafetyStagingDataset, MedicationSafetyImportResult | None]:
    dataset = load_medication_safety_staging_dataset(
        marker_path=marker_path,
        allow_pending=allow_pending,
    )
    if dry_run:
        return dataset, None
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await import_medication_safety_staging_dataset(dataset)
        return dataset, result
    finally:
        await Tortoise.close_connections()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검증된 단일 약물 안전 규칙 staging 세대를 PENDING 상태로 적재합니다.")
    parser.add_argument(
        "--marker",
        type=Path,
        default=(
            PROJECT_ROOT / "data" / "knowledge" / "processed" / "staging" / "medication-safety-v2" / "current.json"
        ),
    )
    parser.add_argument("--allow-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        dataset, result = asyncio.run(
            _run_import(
                marker_path=args.marker,
                allow_pending=args.allow_pending,
                dry_run=args.dry_run,
            )
        )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    payload: dict[str, object] = {
        "dataset_version": dataset.dataset_version,
        "generation_id": dataset.generation_id,
        "candidate_count": len(dataset.candidates),
        "candidate_sha256": dataset.candidate_sha256,
        "ready_for_rdb_import": dataset.ready_for_rdb_import,
        "dry_run": args.dry_run,
    }
    if result is not None:
        payload["database"] = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
