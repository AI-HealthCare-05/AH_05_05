import csv
import hashlib
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    InteractionRiskLevel,
    InteractionRuleCandidate,
    InteractionSourceRecord,
    normalize_interaction_name,
)

_REQUIRED_COLUMNS = frozenset(
    {
        "DUR일련번호",
        "DUR유형",
        "DUR성분코드",
        "DUR성분명",
        "금기내용",
        "병용금기DUR성분코드",
        "병용금기DUR성분명",
        "상태",
    }
)

_REQUIRED_VALUE_COLUMNS = (
    "DUR일련번호",
    "DUR성분코드",
    "DUR성분명",
    "금기내용",
    "병용금기DUR성분코드",
    "병용금기DUR성분명",
)

_MALFORMED_ROW_KEY = "__interaction_staging_csv_error__"
_SOURCE_LINE_KEY = "__interaction_staging_source_line__"
_SAFE_DATASET_VERSION = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
)


class SkippedInteractionSourceRow(BaseModel):
    source_line_number: int = Field(ge=2)
    record_id: str | None = None
    reason: str = Field(min_length=1)
    detail: str | None = None


class InteractionStagingResult(BaseModel):
    generation_id: str = Field(min_length=16, max_length=64)
    dataset_version: str
    input_row_count: int = Field(ge=0)
    accepted_row_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    duplicate_merged_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    skipped_rows: list[SkippedInteractionSourceRow] = Field(
        default_factory=list
    )
    candidates_path: Path
    quality_report_path: Path
    current_marker_path: Path
    ready_for_rdb_import: bool = False


class InteractionStagingService:
    """구조화된 DUR 병용금기를 검수 대기 RDBMS 후보로 변환한다."""

    def __init__(
        self,
        *,
        source_id: str,
        document_id: str,
    ) -> None:
        self._source_id = _require_text(source_id, "source_id")
        self._document_id = _require_text(document_id, "document_id")

    def build(
        self,
        *,
        input_path: Path,
        output_root: Path,
        dataset_version: str,
    ) -> InteractionStagingResult:
        normalized_version = validate_interaction_dataset_version(
            dataset_version
        )
        source_path = Path(input_path)
        if not source_path.is_file():
            raise ValueError(f"DUR 병용금기 CSV를 찾을 수 없습니다: {source_path}")

        rows, fieldnames = self._read_rows(source_path)
        missing_columns = sorted(_REQUIRED_COLUMNS.difference(fieldnames))
        if missing_columns:
            raise ValueError(
                "DUR 병용금기 CSV 필수 컬럼이 없습니다: "
                + ", ".join(missing_columns)
            )

        candidates_by_pair: dict[str, InteractionRuleCandidate] = {}
        skipped_reasons: Counter[str] = Counter()
        skipped_rows: list[SkippedInteractionSourceRow] = []
        accepted_row_count = 0

        for row in rows:
            skip_reason = self._skip_reason(row)
            if skip_reason is not None:
                skipped_reasons[skip_reason] += 1
                skipped_rows.append(
                    self._build_skipped_row(
                        row,
                        reason=skip_reason,
                        detail=self._skip_detail(row, skip_reason),
                    )
                )
                continue

            try:
                candidate = self._to_candidate(
                    row,
                    dataset_version=normalized_version,
                )
            except ValidationError as error:
                reason = "ROW_VALIDATION_ERROR"
                skipped_reasons[reason] += 1
                first_error = error.errors()[0]
                skipped_rows.append(
                    self._build_skipped_row(
                        row,
                        reason=reason,
                        detail=str(first_error["msg"]),
                    )
                )
                continue
            accepted_row_count += 1
            previous = candidates_by_pair.get(candidate.pair_key)
            if previous is None:
                candidates_by_pair[candidate.pair_key] = candidate
                continue

            candidates_by_pair[candidate.pair_key] = (
                InteractionRuleCandidate(
                    dataset_version=previous.dataset_version,
                    pair_type=previous.pair_type,
                    left_entity=previous.left_entity,
                    right_entity=previous.right_entity,
                    risk_level=previous.risk_level,
                    effect_summaries=[
                        *previous.effect_summaries,
                        *candidate.effect_summaries,
                    ],
                    source_records=[
                        *previous.source_records,
                        *candidate.source_records,
                    ],
                    evidence_chunk_ids=[
                        *previous.evidence_chunk_ids,
                        *candidate.evidence_chunk_ids,
                    ],
                )
            )

        candidates = sorted(
            candidates_by_pair.values(),
            key=lambda item: item.pair_key,
        )
        candidate_content = "".join(
            f"{candidate.model_dump_json()}\n" for candidate in candidates
        )
        generation_id = self._build_generation_id(
            dataset_version=normalized_version,
            candidate_content=candidate_content,
            input_row_count=len(rows),
            accepted_row_count=accepted_row_count,
            skipped_rows=skipped_rows,
        )
        generation_root = (
            Path("staging") / normalized_version / generation_id
        )
        result = InteractionStagingResult(
            generation_id=generation_id,
            dataset_version=normalized_version,
            input_row_count=len(rows),
            accepted_row_count=accepted_row_count,
            candidate_count=len(candidates),
            duplicate_merged_count=(accepted_row_count - len(candidates)),
            skipped_reason_counts=dict(sorted(skipped_reasons.items())),
            skipped_rows=skipped_rows,
            candidates_path=(
                generation_root / "interaction_rule_candidates.jsonl"
            ),
            quality_report_path=(
                generation_root / "interaction-staging-quality.json"
            ),
            current_marker_path=(
                Path("staging") / normalized_version / "current.json"
            ),
        )
        self._publish_generation(
            output_root=Path(output_root),
            candidate_content=candidate_content,
            result=result,
        )
        return result

    @staticmethod
    def _read_rows(
        input_path: Path,
    ) -> tuple[list[dict[str, str]], set[str]]:
        physical_lines = input_path.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if not physical_lines:
            return [], set()

        header = next(csv.reader([physical_lines[0]], strict=True))
        rows: list[dict[str, str]] = []
        buffer: list[str] = []
        buffer_start = 2
        for source_line_number, line in enumerate(
            physical_lines[1:],
            start=2,
        ):
            if buffer and _is_dur_record_start(line, header=header):
                rows.append(
                    _malformed_row(
                        buffer,
                        source_line_number=buffer_start,
                        error="UNCLOSED_QUOTE",
                    )
                )
                buffer = []

            if not buffer:
                buffer_start = source_line_number
            buffer.append(line)
            values = _parse_single_csv_record(buffer)
            if values is None:
                continue
            if len(values) != len(header):
                rows.append(
                    _malformed_row(
                        buffer,
                        source_line_number=buffer_start,
                        error="COLUMN_COUNT_MISMATCH",
                    )
                )
            else:
                row = dict(zip(header, values, strict=True))
                row[_SOURCE_LINE_KEY] = str(buffer_start)
                rows.append(row)
            buffer = []

        if buffer:
            rows.append(
                _malformed_row(
                    buffer,
                    source_line_number=buffer_start,
                    error="CSV_PARSE_ERROR",
                )
            )
        return rows, set(header)

    @staticmethod
    def _skip_reason(row: dict[str, str]) -> str | None:
        if _MALFORMED_ROW_KEY in row:
            return "MALFORMED_CSV_ROW"
        if normalize_interaction_name(row.get("상태") or "") != "정상":
            return "INACTIVE_STATUS"
        if normalize_interaction_name(row.get("DUR유형") or "") != "병용금기":
            return "UNEXPECTED_DUR_TYPE"
        if any(
            _is_missing_value(row.get(column))
            for column in _REQUIRED_VALUE_COLUMNS
        ):
            return "MISSING_REQUIRED_VALUE"
        return None

    @staticmethod
    def _skip_detail(
        row: dict[str, str],
        reason: str,
    ) -> str | None:
        if reason == "MALFORMED_CSV_ROW":
            return row.get(_MALFORMED_ROW_KEY)
        if reason == "MISSING_REQUIRED_VALUE":
            missing = [
                column
                for column in _REQUIRED_VALUE_COLUMNS
                if _is_missing_value(row.get(column))
            ]
            return "누락 필드: " + ", ".join(missing)
        return None

    @staticmethod
    def _build_skipped_row(
        row: dict[str, str],
        *,
        reason: str,
        detail: str | None,
    ) -> SkippedInteractionSourceRow:
        record_id = normalize_interaction_name(
            row.get("DUR일련번호") or ""
        )
        return SkippedInteractionSourceRow(
            source_line_number=int(row[_SOURCE_LINE_KEY]),
            record_id=record_id or None,
            reason=reason,
            detail=detail,
        )

    def _to_candidate(
        self,
        row: dict[str, str],
        *,
        dataset_version: str,
    ) -> InteractionRuleCandidate:
        return InteractionRuleCandidate(
            dataset_version=dataset_version,
            pair_type=InteractionPairType.DRUG_DRUG,
            left_entity=InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name=row["DUR성분명"],
                source_code=row["DUR성분코드"],
            ),
            right_entity=InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name=row["병용금기DUR성분명"],
                source_code=row["병용금기DUR성분코드"],
            ),
            risk_level=InteractionRiskLevel.CONTRAINDICATED,
            effect_summaries=[row["금기내용"]],
            source_records=[
                InteractionSourceRecord(
                    source_id=self._source_id,
                    document_id=self._document_id,
                    record_id=row["DUR일련번호"],
                    raw_effect_text=row["금기내용"],
                )
            ],
        )

    @staticmethod
    def _build_generation_id(
        *,
        dataset_version: str,
        candidate_content: str,
        input_row_count: int,
        accepted_row_count: int,
        skipped_rows: list[SkippedInteractionSourceRow],
    ) -> str:
        generation_contract = {
            "dataset_version": dataset_version,
            "candidate_content_sha256": hashlib.sha256(
                candidate_content.encode("utf-8")
            ).hexdigest(),
            "input_row_count": input_row_count,
            "accepted_row_count": accepted_row_count,
            "skipped_rows": [
                row.model_dump(mode="json") for row in skipped_rows
            ],
        }
        canonical = json.dumps(
            generation_contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _publish_generation(
        *,
        output_root: Path,
        candidate_content: str,
        result: InteractionStagingResult,
    ) -> None:
        generation_root = (
            output_root
            / "staging"
            / result.dataset_version
            / result.generation_id
        ).resolve()
        resolved_output_root = output_root.resolve()
        if not generation_root.is_relative_to(resolved_output_root):
            raise ValueError(
                "staging generation 경로가 output_root를 벗어났습니다."
            )
        generation_parent = generation_root.parent
        generation_parent.mkdir(parents=True, exist_ok=True)

        if not generation_root.exists():
            with tempfile.TemporaryDirectory(
                dir=generation_parent,
                prefix=".tmp-",
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                (temporary_root / "interaction_rule_candidates.jsonl").write_text(
                    candidate_content,
                    encoding="utf-8",
                )
                (temporary_root / "interaction-staging-quality.json").write_text(
                    result.model_dump_json(indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary_root.replace(generation_root)

        marker = {
            "generation_id": result.generation_id,
            "dataset_version": result.dataset_version,
            "candidates_path": str(result.candidates_path),
            "quality_report_path": str(result.quality_report_path),
        }
        marker_path = (
            output_root / result.current_marker_path
        ).resolve()
        if not marker_path.is_relative_to(resolved_output_root):
            raise ValueError(
                "staging marker 경로가 output_root를 벗어났습니다."
            )
        _write_text_atomic(
            marker_path,
            json.dumps(
                marker,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )


def _require_text(value: str, field_name: str) -> str:
    normalized = normalize_interaction_name(value)
    if not normalized:
        raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
    return normalized


def validate_interaction_dataset_version(value: str) -> str:
    normalized = _require_text(value, "dataset_version")
    if _SAFE_DATASET_VERSION.fullmatch(normalized) is None:
        raise ValueError(
            "dataset_version은 영문자·숫자로 시작하는 "
            "100자 이하의 안전한 slug여야 합니다."
        )
    return normalized


def _is_missing_value(value: str | None) -> bool:
    return normalize_interaction_name(value or "") in {"", "-"}


def _is_dur_record_start(
    line: str,
    *,
    header: list[str],
) -> bool:
    required_prefix_fields = (
        "DUR일련번호",
        "DUR유형",
        "DUR성분코드",
    )
    if any(field not in header for field in required_prefix_fields):
        return False

    field_indexes = {
        field: header.index(field) for field in required_prefix_fields
    }
    single_compound_index = (
        header.index("단일복합구분코드")
        if "단일복합구분코드" in header
        else None
    )
    last_prefix_index = max(
        [
            *field_indexes.values(),
            *(
                [single_compound_index]
                if single_compound_index is not None
                else []
            ),
        ]
    )
    values = line.split(",", maxsplit=last_prefix_index + 1)
    if len(values) <= last_prefix_index:
        return False

    record_id = values[field_indexes["DUR일련번호"]].strip()
    dur_type = normalize_interaction_name(
        values[field_indexes["DUR유형"]]
    )
    ingredient_code = values[
        field_indexes["DUR성분코드"]
    ].strip()
    if re.fullmatch(r"\d+", record_id) is None:
        return False
    if dur_type != "병용금기":
        return False
    if re.fullmatch(r"D\d+", ingredient_code) is None:
        return False
    if single_compound_index is not None:
        single_compound = normalize_interaction_name(
            values[single_compound_index]
        )
        if single_compound not in {"단일", "복합"}:
            return False
    return True


def _parse_single_csv_record(lines: list[str]) -> list[str] | None:
    try:
        records = list(csv.reader(["\n".join(lines)], strict=True))
    except csv.Error:
        return None
    if len(records) != 1:
        return None
    return records[0]


def _malformed_row(
    lines: list[str],
    *,
    source_line_number: int,
    error: str,
) -> dict[str, str]:
    first_line = lines[0] if lines else ""
    return {
        _MALFORMED_ROW_KEY: error,
        _SOURCE_LINE_KEY: str(source_line_number),
        "DUR일련번호": first_line.partition(",")[0],
    }


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)
