from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import ValidationError
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_worker.schemas.interaction import (  # noqa: E402
    InteractionRuleCandidate,
)
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.enums import (  # noqa: E402
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionPairType,
    InteractionReviewStatus,
    InteractionRiskLevel,
)
from app.models.interactions import (  # noqa: E402
    InteractionEntity,
    InteractionEntityIdentifier,
    InteractionRule,
    InteractionRuleSource,
)


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class InteractionStagingDataset:
    dataset_version: str
    generation_id: str
    candidates: list[InteractionRuleCandidate]
    ready_for_rdb_import: bool
    candidate_sha256: str = ""
    candidates_path: Path | None = None


@dataclass(frozen=True)
class InteractionImportResult:
    candidates: int
    entities_created: int
    identifiers_created: int
    rules_created: int
    sources_created: int

    @property
    def total_created(self) -> int:
        return self.entities_created + self.identifiers_created + self.rules_created + self.sources_created


def load_staging_dataset(
    *,
    marker_path: Path,
    allow_pending: bool,
    processed_root: Path | None = None,
) -> InteractionStagingDataset:
    marker_path = marker_path.resolve()
    marker = _read_json_object(marker_path)
    root = processed_root.resolve() if processed_root is not None else marker_path.parents[2]
    dataset_version = _required_text(marker, "dataset_version")
    generation_id = _required_text(marker, "generation_id")
    expected_marker = (root / "staging" / dataset_version / "current.json").resolve()
    if marker_path != expected_marker:
        raise ImportValidationError("current marker는 processed/staging/<version>/current.json 경로에 있어야 합니다.")
    candidates_path = _resolve_managed_path(
        root,
        _required_text(marker, "candidates_path"),
    )
    quality_path = _resolve_managed_path(
        root,
        _required_text(marker, "quality_report_path"),
    )
    quality = _read_json_object(quality_path)
    if quality.get("dataset_version") != dataset_version or quality.get("generation_id") != generation_id:
        raise ImportValidationError("current marker와 품질 보고서의 세대 정보가 일치하지 않습니다.")
    quality_candidates_path = _resolve_managed_path(
        root,
        _required_text(quality, "candidates_path"),
    )
    if quality_candidates_path != candidates_path:
        raise ImportValidationError("current marker와 품질 보고서의 후보 경로가 일치하지 않습니다.")

    ready = quality.get("ready_for_rdb_import") is True
    if not ready and not allow_pending:
        raise ImportValidationError("검수 대기 후보를 적재하려면 --allow-pending이 필요합니다.")
    candidates = _read_candidates(candidates_path)
    if quality.get("candidate_count") != len(candidates):
        raise ImportValidationError("품질 보고서와 후보 파일의 건수가 일치하지 않습니다.")
    if any(candidate.dataset_version != dataset_version for candidate in candidates):
        raise ImportValidationError("후보의 dataset_version이 current marker와 일치하지 않습니다.")
    if len({candidate.pair_key for candidate in candidates}) != len(candidates):
        raise ImportValidationError("후보 파일에 중복 pair_key가 있습니다.")
    if any(candidate.evidence_chunk_ids for candidate in candidates):
        raise ImportValidationError("현재 적재기는 근거 청크 연결이 없는 후보만 지원합니다.")
    _validate_candidates(candidates)
    return InteractionStagingDataset(
        dataset_version=dataset_version,
        generation_id=generation_id,
        candidates=candidates,
        ready_for_rdb_import=ready,
        candidate_sha256=_sha256_file(candidates_path),
        candidates_path=candidates_path,
    )


async def upsert_candidates(
    candidates: list[InteractionRuleCandidate],
    *,
    batch_size: int = 500,
) -> InteractionImportResult:
    if batch_size <= 0:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    if not candidates:
        return InteractionImportResult(0, 0, 0, 0, 0)
    _validate_candidates(candidates)

    async with in_transaction() as connection:
        return await _upsert_candidates_using_connection(
            candidates,
            connection=connection,
            batch_size=batch_size,
        )


async def import_staging_dataset(
    dataset: InteractionStagingDataset,
    *,
    batch_size: int = 500,
) -> InteractionImportResult:
    if batch_size <= 0:
        raise ValueError("batch_size는 1 이상이어야 합니다.")

    async with in_transaction() as connection:
        result = await _upsert_candidates_using_connection(
            dataset.candidates,
            connection=connection,
            batch_size=batch_size,
        )
        stored_count = (
            await InteractionRule.filter(
                rule_dataset_version=dataset.dataset_version,
            )
            .using_db(connection)
            .count()
        )
        if stored_count != len(dataset.candidates):
            raise RuntimeError(
                "상호작용 규칙 적재 건수가 후보 건수와 일치하지 않습니다: "
                f"expected={len(dataset.candidates)}, actual={stored_count}"
            )
        return result


async def _upsert_candidates_using_connection(
    candidates: list[InteractionRuleCandidate],
    *,
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> InteractionImportResult:
    _validate_candidates(candidates)
    if not candidates:
        return InteractionImportResult(0, 0, 0, 0, 0)

    entities_by_key, entities_created = await _upsert_entities(
        candidates,
        connection,
        batch_size,
    )
    identifiers_created = await _upsert_identifiers(
        candidates,
        entities_by_key,
        connection,
        batch_size,
    )
    rules_by_key, rules_created = await _upsert_rules(
        candidates,
        entities_by_key,
        connection,
        batch_size,
    )
    sources_created = await _upsert_sources(
        candidates,
        rules_by_key,
        connection,
        batch_size,
    )

    return InteractionImportResult(
        candidates=len(candidates),
        entities_created=entities_created,
        identifiers_created=identifiers_created,
        rules_created=rules_created,
        sources_created=sources_created,
    )


async def _upsert_entities(
    candidates: list[InteractionRuleCandidate],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> tuple[dict[tuple[str, str], InteractionEntity], int]:
    entity_specs = _collect_entity_specs(candidates)
    existing = await _load_entities(
        entity_specs,
        connection,
        batch_size,
    )
    entities_by_key = {(entity.entity_kind.value, entity.normalized_name): entity for entity in existing}
    missing = [
        InteractionEntity(
            entity_kind=InteractionEntityKind(kind),
            canonical_name=display_name,
            normalized_name=normalized_name,
        )
        for (kind, normalized_name), display_name in entity_specs.items()
        if (kind, normalized_name) not in entities_by_key
    ]
    if missing:
        await InteractionEntity.bulk_create(
            missing,
            batch_size=batch_size,
            using_db=connection,
        )
        existing = await _load_entities(
            entity_specs,
            connection,
            batch_size,
        )
        entities_by_key = {(entity.entity_kind.value, entity.normalized_name): entity for entity in existing}
    return entities_by_key, len(missing)


async def _upsert_identifiers(
    candidates: list[InteractionRuleCandidate],
    entities_by_key: dict[tuple[str, str], InteractionEntity],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> int:
    specs = _collect_identifier_specs(candidates, entities_by_key)
    existing = await _load_identifiers(specs, connection, batch_size)
    owner_by_key = {
        (identifier.source_id, identifier.source_code): (identifier.interaction_entity_id) for identifier in existing
    }
    new_identifiers: list[InteractionEntityIdentifier] = []
    for source_id, source_code, entity_id in specs:
        owner_id = owner_by_key.get((source_id, source_code))
        if owner_id is not None and owner_id != entity_id:
            raise ImportValidationError(
                f"출처 코드 {source_id}:{source_code}가 다른 상호작용 주체에 연결되어 있습니다."
            )
        if owner_id is None:
            new_identifiers.append(
                InteractionEntityIdentifier(
                    interaction_entity_id=entity_id,
                    source_id=source_id,
                    source_code=source_code,
                )
            )
    if new_identifiers:
        await InteractionEntityIdentifier.bulk_create(
            new_identifiers,
            batch_size=batch_size,
            using_db=connection,
        )
    return len(new_identifiers)


async def _upsert_rules(
    candidates: list[InteractionRuleCandidate],
    entities_by_key: dict[tuple[str, str], InteractionEntity],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> tuple[dict[tuple[str, str], InteractionRule], int]:
    dataset_versions = {candidate.dataset_version for candidate in candidates}
    pair_keys = {candidate.pair_key for candidate in candidates}
    existing = await _load_rules(
        pair_keys,
        dataset_versions,
        connection,
        batch_size,
    )
    rules_by_key = {(rule.pair_key, rule.rule_dataset_version): rule for rule in existing}
    new_rules: list[InteractionRule] = []
    for candidate in candidates:
        left, right = _resolve_candidate_entities(
            candidate,
            entities_by_key,
        )
        rule = rules_by_key.get((candidate.pair_key, candidate.dataset_version))
        if rule is not None:
            _validate_immutable_rule(rule, candidate, left, right)
            continue
        new_rules.append(
            InteractionRule(
                pair_key=candidate.pair_key,
                pair_type=InteractionPairType(candidate.pair_type.value),
                left_entity_id=left.id,
                right_entity_id=right.id,
                risk_level=InteractionRiskLevel(candidate.risk_level.value),
                review_status=InteractionReviewStatus.PENDING,
                rule_dataset_version=candidate.dataset_version,
                extraction_method=InteractionExtractionMethod(candidate.extraction_method.value),
            )
        )
    if new_rules:
        await InteractionRule.bulk_create(
            new_rules,
            batch_size=batch_size,
            using_db=connection,
        )
        existing = await _load_rules(
            pair_keys,
            dataset_versions,
            connection,
            batch_size,
        )
        rules_by_key = {(rule.pair_key, rule.rule_dataset_version): rule for rule in existing}
    return rules_by_key, len(new_rules)


async def _upsert_sources(
    candidates: list[InteractionRuleCandidate],
    rules_by_key: dict[tuple[str, str], InteractionRule],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> int:
    existing = await _load_sources(
        [rule.id for rule in rules_by_key.values()],
        connection,
        batch_size,
    )
    sources_by_key = {
        (
            source.interaction_rule_id,
            source.source_id,
            source.document_id,
            source.record_id,
        ): source
        for source in existing
    }
    new_sources: list[InteractionRuleSource] = []
    for candidate in candidates:
        rule = rules_by_key[(candidate.pair_key, candidate.dataset_version)]
        fallback_effect = "\n".join(candidate.effect_summaries)
        for source in candidate.source_records:
            key = (
                rule.id,
                source.source_id,
                source.document_id,
                source.record_id,
            )
            raw_effect_text = source.raw_effect_text or fallback_effect
            stored = sources_by_key.get(key)
            if stored is not None:
                _validate_immutable_source(
                    stored,
                    raw_effect_text,
                    source.source_url,
                )
                continue
            new_sources.append(
                InteractionRuleSource(
                    interaction_rule_id=rule.id,
                    source_id=source.source_id,
                    document_id=source.document_id,
                    record_id=source.record_id,
                    raw_effect_text=raw_effect_text,
                    source_url=source.source_url,
                )
            )
    if new_sources:
        await InteractionRuleSource.bulk_create(
            new_sources,
            batch_size=batch_size,
            using_db=connection,
        )
    return len(new_sources)


def _resolve_candidate_entities(
    candidate: InteractionRuleCandidate,
    entities_by_key: dict[tuple[str, str], InteractionEntity],
) -> tuple[InteractionEntity, InteractionEntity]:
    return (
        entities_by_key[
            (
                candidate.left_entity.kind.value,
                candidate.left_entity.normalized_name,
            )
        ],
        entities_by_key[
            (
                candidate.right_entity.kind.value,
                candidate.right_entity.normalized_name,
            )
        ],
    )


def _validate_immutable_rule(
    rule: InteractionRule,
    candidate: InteractionRuleCandidate,
    left: InteractionEntity,
    right: InteractionEntity,
) -> None:
    actual = (
        rule.pair_type.value,
        rule.left_entity_id,
        rule.right_entity_id,
        rule.risk_level.value,
        rule.extraction_method.value,
    )
    expected = (
        candidate.pair_type.value,
        left.id,
        right.id,
        candidate.risk_level.value,
        candidate.extraction_method.value,
    )
    if actual != expected:
        raise ImportValidationError(
            f"같은 데이터셋 버전의 상호작용 규칙은 불변이어야 합니다: pair_key={candidate.pair_key}"
        )


def _validate_immutable_source(
    source: InteractionRuleSource,
    raw_effect_text: str,
    source_url: str | None,
) -> None:
    if source.raw_effect_text != raw_effect_text or source.source_url != source_url:
        raise ImportValidationError(f"같은 데이터셋 버전의 출처 내용은 불변이어야 합니다: record_id={source.record_id}")


def _validate_candidates(
    candidates: list[InteractionRuleCandidate],
) -> None:
    for candidate in candidates:
        if candidate.review_status.value != InteractionReviewStatus.PENDING.value:
            raise ImportValidationError("자동 생성 상호작용 후보는 PENDING 상태여야 합니다.")
        source_ids = {source.source_id for source in candidate.source_records}
        has_source_code = any(
            entity.source_code is not None
            for entity in (
                candidate.left_entity,
                candidate.right_entity,
            )
        )
        if has_source_code and len(source_ids) != 1:
            raise ImportValidationError("출처 코드가 있는 후보는 하나의 source_id만 가져야 합니다.")


async def _load_entities(
    specs: dict[tuple[str, str], str],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> list[InteractionEntity]:
    names_by_kind: dict[str, list[str]] = {}
    for kind, normalized_name in specs:
        names_by_kind.setdefault(kind, []).append(normalized_name)
    entities: list[InteractionEntity] = []
    for kind, names in names_by_kind.items():
        for start in range(0, len(names), batch_size):
            entities.extend(
                await InteractionEntity.filter(
                    entity_kind=InteractionEntityKind(kind),
                    normalized_name__in=names[start : start + batch_size],
                ).using_db(connection)
            )
    return entities


async def _load_identifiers(
    specs: set[tuple[str, str, int]],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> list[InteractionEntityIdentifier]:
    codes_by_source: dict[str, list[str]] = {}
    for source_id, source_code, _ in specs:
        codes_by_source.setdefault(source_id, []).append(source_code)
    identifiers: list[InteractionEntityIdentifier] = []
    for source_id, codes in codes_by_source.items():
        for start in range(0, len(codes), batch_size):
            identifiers.extend(
                await InteractionEntityIdentifier.filter(
                    source_id=source_id,
                    source_code__in=codes[start : start + batch_size],
                ).using_db(connection)
            )
    return identifiers


async def _load_rules(
    pair_keys: set[str],
    dataset_versions: set[str],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> list[InteractionRule]:
    keys = list(pair_keys)
    rules: list[InteractionRule] = []
    for dataset_version in dataset_versions:
        for start in range(0, len(keys), batch_size):
            rules.extend(
                await InteractionRule.filter(
                    pair_key__in=keys[start : start + batch_size],
                    rule_dataset_version=dataset_version,
                ).using_db(connection)
            )
    return rules


async def _load_sources(
    rule_ids: list[int],
    connection: BaseDBAsyncClient,
    batch_size: int,
) -> list[InteractionRuleSource]:
    sources: list[InteractionRuleSource] = []
    for start in range(0, len(rule_ids), batch_size):
        sources.extend(
            await InteractionRuleSource.filter(interaction_rule_id__in=(rule_ids[start : start + batch_size])).using_db(
                connection
            )
        )
    return sources


def _collect_entity_specs(
    candidates: list[InteractionRuleCandidate],
) -> dict[tuple[str, str], str]:
    specs: dict[tuple[str, str], str] = {}
    for candidate in candidates:
        for entity in (candidate.left_entity, candidate.right_entity):
            specs.setdefault(
                (entity.kind.value, entity.normalized_name),
                entity.display_name,
            )
    return specs


def _collect_identifier_specs(
    candidates: list[InteractionRuleCandidate],
    entities_by_key: dict[tuple[str, str], InteractionEntity],
) -> set[tuple[str, str, int]]:
    specs: set[tuple[str, str, int]] = set()
    for candidate in candidates:
        source_id = candidate.source_records[0].source_id
        for entity in (candidate.left_entity, candidate.right_entity):
            if entity.source_code is None:
                continue
            orm_entity = entities_by_key[(entity.kind.value, entity.normalized_name)]
            specs.add((source_id, entity.source_code, orm_entity.id))
    return specs


def _read_candidates(path: Path) -> list[InteractionRuleCandidate]:
    candidates: list[InteractionRuleCandidate] = []
    try:
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    candidates.append(InteractionRuleCandidate.model_validate_json(line))
                except ValidationError as error:
                    raise ImportValidationError(f"후보 JSONL {line_number}행이 올바르지 않습니다.") from error
    except OSError as error:
        raise ImportValidationError(f"상호작용 후보 파일을 읽을 수 없습니다: {path}") from error
    return candidates


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ImportValidationError(f"상호작용 후보 파일의 SHA-256을 계산할 수 없습니다: {path}") from error
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ImportValidationError(f"JSON 파일을 읽을 수 없습니다: {path}") from error
    if not isinstance(payload, dict):
        raise ImportValidationError(f"JSON 객체가 필요합니다: {path}")
    return payload


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImportValidationError(f"{key} 값이 필요합니다.")
    return value.strip()


def _resolve_managed_path(root: Path, value: str) -> Path:
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ImportValidationError("관리 디렉터리 밖의 경로는 사용할 수 없습니다.")
    return path


async def _run_import(
    *,
    marker_path: Path,
    allow_pending: bool,
    dry_run: bool,
) -> tuple[InteractionStagingDataset, InteractionImportResult | None]:
    dataset = load_staging_dataset(
        marker_path=marker_path,
        allow_pending=allow_pending,
    )
    if dry_run:
        return dataset, None
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await import_staging_dataset(dataset)
        return dataset, result
    finally:
        await Tortoise.close_connections()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("검증된 DUR 상호작용 staging 세대를 PENDING 규칙으로 적재합니다."))
    parser.add_argument(
        "--marker",
        type=Path,
        default=(
            PROJECT_ROOT / "data" / "knowledge" / "processed" / "staging" / "interaction-pilot-v1" / "current.json"
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
