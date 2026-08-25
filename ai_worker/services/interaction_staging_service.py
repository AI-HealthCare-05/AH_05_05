import csv
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

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


class SkippedInteractionSourceRow(BaseModel):
    source_line_number: int = Field(ge=2)
    record_id: str | None = None
    reason: str = Field(min_length=1)


class InteractionStagingResult(BaseModel):
    dataset_version: str
    input_row_count: int = Field(ge=0)
    accepted_row_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    duplicate_merged_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    skipped_rows: list[SkippedInteractionSourceRow] = Field(
        default_factory=list
    )
    candidates_path: Path = Path(
        "records/interaction_rule_candidates.jsonl"
    )
    quality_report_path: Path = Path(
        "reports/interaction-staging-quality.json"
    )
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
        normalized_version = _require_text(
            dataset_version,
            "dataset_version",
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
                record_id = normalize_interaction_name(
                    row.get("DUR일련번호") or ""
                )
                skipped_rows.append(
                    SkippedInteractionSourceRow(
                        source_line_number=int(row[_SOURCE_LINE_KEY]),
                        record_id=record_id or None,
                        reason=skip_reason,
                    )
                )
                continue

            candidate = self._to_candidate(
                row,
                dataset_version=normalized_version,
            )
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
        result = InteractionStagingResult(
            dataset_version=normalized_version,
            input_row_count=len(rows),
            accepted_row_count=accepted_row_count,
            candidate_count=len(candidates),
            duplicate_merged_count=(accepted_row_count - len(candidates)),
            skipped_reason_counts=dict(sorted(skipped_reasons.items())),
            skipped_rows=skipped_rows,
        )
        self._write_outputs(
            output_root=Path(output_root),
            candidates=candidates,
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
        for source_line_number, line in enumerate(
            physical_lines[1:],
            start=2,
        ):
            try:
                values = next(csv.reader([line], strict=True))
            except csv.Error:
                rows.append(
                    {
                        _MALFORMED_ROW_KEY: "CSV_PARSE_ERROR",
                        _SOURCE_LINE_KEY: str(source_line_number),
                        "DUR일련번호": line.partition(",")[0],
                    }
                )
                continue
            if len(values) != len(header):
                rows.append(
                    {
                        _MALFORMED_ROW_KEY: "COLUMN_COUNT_MISMATCH",
                        _SOURCE_LINE_KEY: str(source_line_number),
                        "DUR일련번호": values[0] if values else "",
                    }
                )
                continue
            row = dict(zip(header, values, strict=True))
            row[_SOURCE_LINE_KEY] = str(source_line_number)
            rows.append(row)
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
                )
            ],
        )

    @staticmethod
    def _write_outputs(
        *,
        output_root: Path,
        candidates: list[InteractionRuleCandidate],
        result: InteractionStagingResult,
    ) -> None:
        candidate_path = output_root / result.candidates_path
        quality_path = output_root / result.quality_report_path
        candidate_content = "".join(
            f"{candidate.model_dump_json()}\n" for candidate in candidates
        )
        _write_text_atomic(candidate_path, candidate_content)
        _write_text_atomic(
            quality_path,
            result.model_dump_json(indent=2) + "\n",
        )


def _require_text(value: str, field_name: str) -> str:
    normalized = normalize_interaction_name(value)
    if not normalized:
        raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
    return normalized


def _is_missing_value(value: str | None) -> bool:
    return normalize_interaction_name(value or "") in {"", "-"}


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)
