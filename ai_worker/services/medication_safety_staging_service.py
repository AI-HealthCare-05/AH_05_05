from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, Field

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionRiskLevel,
    normalize_interaction_name,
)
from ai_worker.schemas.medication_safety import (
    MedicationSafetyConditionCandidate,
    MedicationSafetyRuleCandidate,
    MedicationSafetyRuleType,
    MedicationSafetySourceRecord,
    SafetyComparisonOperator,
    SafetyConditionKind,
)

_SAFE_DATASET_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_MISSING_VALUES = frozenset({"", "-", "없음", "해당없음", "nan", "none"})
_DUR_REQUIRED_COLUMNS = frozenset(
    {
        "DUR일련번호",
        "DUR유형",
        "DUR성분코드",
        "DUR성분명",
        "고시일자",
        "금기내용",
        "제형",
        "연령기준",
        "최대투여기간",
        "1일최대용량",
        "등급",
        "비고",
        "상태",
    }
)
_DAILY_MAX_REQUIRED_COLUMNS = frozenset(
    {
        "성분코드",
        "성분명(한글)",
        "제형코드",
        "제형명",
        "투여경로",
        "투여단위",
        "1일최대투여량",
    }
)
_DUR_TYPE_BY_FILENAME = {
    "DUR임부금기.csv": "임부금기",
    "DUR특정연령대금기.csv": "특정연령대금기",
    "DUR노인주의.csv": "노인주의",
    "DUR용량주의.csv": "용량주의",
    "DUR투여기간주의.csv": "투여기간주의",
    "DUR첨가제주의.csv": "첨가제주의",
}
_SUPPORTED_SOURCE_FILENAMES = frozenset(
    {
        *_DUR_TYPE_BY_FILENAME,
        "1일최대투여량.csv",
    }
)
_OPERATOR_BY_KOREAN = {
    "미만": SafetyComparisonOperator.LT,
    "이하": SafetyComparisonOperator.LTE,
    "이상": SafetyComparisonOperator.GTE,
    "초과": SafetyComparisonOperator.GT,
}
_DOSE_UNIT_BY_KOREAN = {
    "마이크로그램": "mcg/day",
    "밀리그램": "mg/day",
    "그램": "g/day",
    "방울": "drop/day",
    "밀리리터": "mL/day",
    "리터": "L/day",
    "정": "tablet/day",
    "캡슐": "capsule/day",
    "포": "packet/day",
    "회": "dose/day",
    "병": "bottle/day",
    "앰플": "ampoule/day",
    "바이알": "vial/day",
    "매": "sheet/day",
    "개": "unit/day",
    "환": "pill/day",
    "프리필드시린지": "prefilled-syringe/day",
    "프리필드펜": "prefilled-pen/day",
    "시린지": "syringe/day",
}
_AMOUNT_PATTERN = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)"
    r"(?P<unit>마이크로그램|밀리그램|밀리리터|그램|리터|방울|캡슐|프리필드시린지|프리필드펜|바이알|시린지|앰플|정|포|회|병|매|개|환)"
)
_AGE_PATTERN = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>세|개월|주|일)(?P<operator>미만|이하|이상|초과)$")
_DURATION_PATTERN = re.compile(r"^(?P<days>\d+(?:\.\d+)?)일$")


class SkippedMedicationSafetyRow(BaseModel):
    document_id: str
    source_line_number: int = Field(ge=2)
    record_id: str | None = None
    reason: str = Field(min_length=1)
    detail: str | None = None


class MedicationSafetyStagingResult(BaseModel):
    generation_id: str = Field(min_length=16, max_length=64)
    dataset_version: str
    input_row_count: int = Field(ge=0)
    accepted_row_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    duplicate_merged_count: int = Field(ge=0)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    skipped_rows: list[SkippedMedicationSafetyRow] = Field(default_factory=list)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates_path: Path
    quality_report_path: Path
    current_marker_path: Path
    ready_for_rdb_import: bool = False


class _SkipRowError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


class MedicationSafetyStagingService:
    """7종 식약처 구조화 자료를 검수 대기 단일 약물 규칙으로 변환한다."""

    def __init__(self, *, source_id: str = "mfds_drug_records") -> None:
        self._source_id = _required_text(source_id, "source_id")

    def build(
        self,
        *,
        input_paths: list[Path],
        output_root: Path,
        dataset_version: str,
    ) -> MedicationSafetyStagingResult:
        normalized_version = validate_medication_safety_dataset_version(dataset_version)
        normalized_paths = [Path(path) for path in input_paths]
        source_names = [path.name for path in normalized_paths]
        if len(source_names) != len(_SUPPORTED_SOURCE_FILENAMES) or set(source_names) != _SUPPORTED_SOURCE_FILENAMES:
            raise ValueError("지원하는 7종 CSV를 각각 정확히 한 번씩 입력해야 합니다.")

        candidates_by_key: dict[str, MedicationSafetyRuleCandidate] = {}
        skipped_rows: list[SkippedMedicationSafetyRow] = []
        skipped_reasons: Counter[str] = Counter()
        source_type_counts: Counter[str] = Counter()
        input_row_count = 0
        accepted_row_count = 0

        for input_path in sorted(normalized_paths, key=lambda path: path.name):
            if not input_path.is_file():
                raise ValueError(f"구조화 의약품 CSV를 찾을 수 없습니다: {input_path}")
            rows, fieldnames = self._read_rows(input_path)
            self._validate_columns(input_path.name, fieldnames)
            source_type_counts[input_path.name] += len(rows)
            input_row_count += len(rows)

            for source_line_number, row in enumerate(rows, start=2):
                try:
                    candidate = self._to_candidate(
                        document_id=input_path.name,
                        row=row,
                        source_line_number=source_line_number,
                        dataset_version=normalized_version,
                    )
                except _SkipRowError as error:
                    skipped_reasons[error.reason] += 1
                    skipped_rows.append(
                        SkippedMedicationSafetyRow(
                            document_id=input_path.name,
                            source_line_number=source_line_number,
                            record_id=_optional_text(row.get("DUR일련번호")),
                            reason=error.reason,
                            detail=error.detail,
                        )
                    )
                    continue
                accepted_row_count += 1
                previous = candidates_by_key.get(candidate.rule_key)
                if previous is None:
                    candidates_by_key[candidate.rule_key] = candidate
                else:
                    candidates_by_key[candidate.rule_key] = previous.model_copy(
                        update={"sources": [*previous.sources, *candidate.sources]}
                    )
                    candidates_by_key[candidate.rule_key] = MedicationSafetyRuleCandidate.model_validate(
                        candidates_by_key[candidate.rule_key].model_dump()
                    )

        candidates = sorted(candidates_by_key.values(), key=lambda item: item.rule_key)
        candidate_content = "".join(candidate.model_dump_json() + "\n" for candidate in candidates)
        candidate_sha256 = hashlib.sha256(candidate_content.encode("utf-8")).hexdigest()
        generation_payload = json.dumps(
            {
                "dataset_version": normalized_version,
                "candidate_sha256": candidate_sha256,
                "input_row_count": input_row_count,
                "accepted_row_count": accepted_row_count,
                "skipped_rows": [item.model_dump(mode="json") for item in skipped_rows],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        generation_id = hashlib.sha256(generation_payload.encode("utf-8")).hexdigest()
        generation_root = Path("staging") / normalized_version / generation_id
        result = MedicationSafetyStagingResult(
            generation_id=generation_id,
            dataset_version=normalized_version,
            input_row_count=input_row_count,
            accepted_row_count=accepted_row_count,
            candidate_count=len(candidates),
            duplicate_merged_count=accepted_row_count - len(candidates),
            source_type_counts=dict(sorted(source_type_counts.items())),
            skipped_reason_counts=dict(sorted(skipped_reasons.items())),
            skipped_rows=skipped_rows,
            candidate_sha256=candidate_sha256,
            candidates_path=generation_root / "medication_safety_rule_candidates.jsonl",
            quality_report_path=generation_root / "medication-safety-staging-quality.json",
            current_marker_path=Path("staging") / normalized_version / "current.json",
        )
        self._publish_generation(
            output_root=Path(output_root),
            candidate_content=candidate_content,
            result=result,
        )
        return result

    @staticmethod
    def _read_rows(input_path: Path) -> tuple[list[dict[str, str]], set[str]]:
        with input_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = {name for name in (reader.fieldnames or []) if name}
            return list(reader), fieldnames

    @staticmethod
    def _validate_columns(document_id: str, fieldnames: set[str]) -> None:
        required = _DAILY_MAX_REQUIRED_COLUMNS if document_id == "1일최대투여량.csv" else _DUR_REQUIRED_COLUMNS
        missing = sorted(required.difference(fieldnames))
        if missing:
            raise ValueError(f"{document_id} 필수 컬럼이 없습니다: {', '.join(missing)}")
        if document_id != "1일최대투여량.csv" and document_id not in _DUR_TYPE_BY_FILENAME:
            raise ValueError(f"지원하지 않는 구조화 의약품 CSV입니다: {document_id}")

    def _to_candidate(
        self,
        *,
        document_id: str,
        row: dict[str, str],
        source_line_number: int,
        dataset_version: str,
    ) -> MedicationSafetyRuleCandidate:
        if document_id == "1일최대투여량.csv":
            return self._daily_max_candidate(
                document_id=document_id,
                row=row,
                source_line_number=source_line_number,
                dataset_version=dataset_version,
            )
        return self._dur_candidate(
            document_id=document_id,
            row=row,
            dataset_version=dataset_version,
        )

    def _dur_candidate(
        self,
        *,
        document_id: str,
        row: dict[str, str],
        dataset_version: str,
    ) -> MedicationSafetyRuleCandidate:
        if _normalized_value(row.get("상태")) != "정상":
            raise _SkipRowError("INACTIVE_STATUS")
        expected_type = _DUR_TYPE_BY_FILENAME[document_id]
        if _normalized_value(row.get("DUR유형")) != expected_type:
            raise _SkipRowError("UNEXPECTED_DUR_TYPE")

        record_id = _required_row_value(row, "DUR일련번호")
        source_code = _required_row_value(row, "DUR성분코드")
        name = _required_row_value(row, "DUR성분명")
        entity = InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name=name,
            source_code=source_code,
        )
        raw_effect = _first_present(row.get("금기내용"), row.get("비고"))
        conditions: list[MedicationSafetyConditionCandidate]

        if expected_type == "임부금기":
            rule_type = MedicationSafetyRuleType.PREGNANCY_CONTRAINDICATION
            risk_level = _pregnancy_risk(row.get("등급"))
            conditions = [_text_condition(SafetyConditionKind.PREGNANCY_STATUS, "PREGNANT")]
            guidance = (
                f"{name}은 임신 중 금기 또는 주의 대상으로 분류된 성분입니다. 복용 전 의료진 또는 약사와 상담하세요."
            )
        elif expected_type == "특정연령대금기":
            rule_type = MedicationSafetyRuleType.AGE_CONTRAINDICATION
            risk_level = InteractionRiskLevel.CONTRAINDICATED
            conditions = [_parse_age_condition(_required_row_value(row, "연령기준"))]
            guidance = f"{name}은 특정 연령에서 사용이 제한되는 성분입니다. 대상 연령의 복용 여부를 의료진 또는 약사와 확인하세요."
        elif expected_type == "노인주의":
            rule_type = MedicationSafetyRuleType.ELDERLY_CAUTION
            risk_level = InteractionRiskLevel.CAUTION
            conditions = [
                MedicationSafetyConditionCandidate(
                    condition_group_no=1,
                    condition_order=1,
                    condition_kind=SafetyConditionKind.AGE_YEARS,
                    comparison_operator=SafetyComparisonOperator.GTE,
                    value_min=65,
                    unit="year",
                )
            ]
            guidance = f"{name}은 고령자에게 주의가 필요한 성분입니다. 복용 전 의료진 또는 약사와 확인하세요."
        elif expected_type == "용량주의":
            rule_type = MedicationSafetyRuleType.DOSE_CAUTION
            risk_level = InteractionRiskLevel.HIGH_CAUTION
            amount, unit = _parse_amount(_required_row_value(row, "1일최대용량"))
            conditions = [_numeric_condition(SafetyConditionKind.DAILY_DOSE, amount, unit)]
            conditions.extend(_form_and_route_conditions(row.get("제형"), row.get("비고"), start_order=2))
            guidance = f"{name}은 1일 투여량에 주의가 필요한 성분입니다. 처방 용량을 임의로 변경하지 마세요."
        elif expected_type == "투여기간주의":
            rule_type = MedicationSafetyRuleType.DURATION_CAUTION
            risk_level = InteractionRiskLevel.HIGH_CAUTION
            duration = _required_row_value(row, "최대투여기간")
            match = _DURATION_PATTERN.fullmatch(_compact(duration))
            if match is None:
                raise _SkipRowError("UNSUPPORTED_DURATION_EXPRESSION", duration)
            conditions = [
                _numeric_condition(
                    SafetyConditionKind.DURATION_DAYS,
                    Decimal(match.group("days")),
                    "day",
                )
            ]
            guidance = f"{name}은 최대 투여기간에 주의가 필요한 성분입니다. 처방 기간을 임의로 연장하지 마세요."
        else:
            rule_type = MedicationSafetyRuleType.EXCIPIENT_CAUTION
            risk_level = InteractionRiskLevel.CONTRAINDICATED
            conditions = [_text_condition(SafetyConditionKind.EXCIPIENT_PRESENT, name, present=True)]
            guidance = f"{name} 첨가제는 특정 질환이나 상태에서 주의가 필요합니다. 제품 성분과 원문 주의사항을 의료진 또는 약사와 확인하세요."

        if raw_effect is None:
            raw_effect = _structured_effect_text(
                document_id=document_id,
                row=row,
                conditions=conditions,
            )
        source = MedicationSafetySourceRecord(
            source_id=self._source_id,
            document_id=document_id,
            record_id=record_id,
            raw_effect_text=raw_effect,
            source_published_at=_parse_date(row.get("고시일자")),
        )
        return MedicationSafetyRuleCandidate(
            dataset_version=dataset_version,
            entity=entity,
            rule_type=rule_type,
            risk_level=risk_level,
            guidance_text=guidance,
            conditions=conditions,
            sources=[source],
        )

    def _daily_max_candidate(
        self,
        *,
        document_id: str,
        row: dict[str, str],
        source_line_number: int,
        dataset_version: str,
    ) -> MedicationSafetyRuleCandidate:
        source_code = _required_row_value(row, "성분코드")
        name = _required_row_value(row, "성분명(한글)")
        raw_amount = _required_row_value(row, "1일최대투여량")
        raw_unit = _required_row_value(row, "투여단위")
        try:
            amount = Decimal(_compact(raw_amount))
        except InvalidOperation as error:
            raise _SkipRowError("UNSUPPORTED_DAILY_MAX_AMOUNT", raw_amount) from error
        unit = _DOSE_UNIT_BY_KOREAN.get(_compact(raw_unit))
        if unit is None:
            raise _SkipRowError("UNSUPPORTED_DOSE_UNIT", raw_unit)

        conditions = [_numeric_condition(SafetyConditionKind.DAILY_DOSE, amount, unit)]
        conditions.extend(
            _form_and_route_conditions(
                row.get("제형명"),
                row.get("투여경로"),
                start_order=2,
            )
        )
        record_payload = "|".join(
            [
                source_code,
                _optional_text(row.get("제형코드")) or "-",
                _optional_text(row.get("투여경로")) or "-",
                raw_unit,
                raw_amount,
                str(source_line_number),
            ]
        )
        record_id = hashlib.sha256(record_payload.encode("utf-8")).hexdigest()
        source = MedicationSafetySourceRecord(
            source_id=self._source_id,
            document_id=document_id,
            record_id=record_id,
            raw_effect_text=f"{name} 1일 최대 투여량: {raw_amount}{raw_unit}",
        )
        return MedicationSafetyRuleCandidate(
            dataset_version=dataset_version,
            entity=InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name=name,
                source_code=source_code,
            ),
            rule_type=MedicationSafetyRuleType.DAILY_MAX_DOSE,
            risk_level=InteractionRiskLevel.HIGH_CAUTION,
            guidance_text=f"{name}은 1일 최대 투여량이 정해진 성분입니다. 처방 용량을 임의로 늘리지 마세요.",
            conditions=conditions,
            sources=[source],
        )

    @staticmethod
    def _publish_generation(
        *,
        output_root: Path,
        candidate_content: str,
        result: MedicationSafetyStagingResult,
    ) -> None:
        output_root.mkdir(parents=True, exist_ok=True)
        version_root = output_root / result.candidates_path.parent.parent
        version_root.mkdir(parents=True, exist_ok=True)
        generation_dir = output_root / result.candidates_path.parent
        quality = result.model_dump(mode="json")
        quality_content = json.dumps(quality, ensure_ascii=False, indent=2) + "\n"
        if generation_dir.exists():
            _validate_existing_generation(
                generation_dir=generation_dir,
                candidate_content=candidate_content,
                quality_content=quality_content,
                result=result,
            )
        else:
            temporary_dir = Path(
                tempfile.mkdtemp(
                    prefix=f".{result.generation_id}.",
                    dir=version_root,
                )
            )
            try:
                (temporary_dir / result.candidates_path.name).write_text(
                    candidate_content,
                    encoding="utf-8",
                )
                (temporary_dir / result.quality_report_path.name).write_text(
                    quality_content,
                    encoding="utf-8",
                )
                os.replace(temporary_dir, generation_dir)
            finally:
                if temporary_dir.exists():
                    shutil.rmtree(temporary_dir)

        marker = {
            "dataset_version": result.dataset_version,
            "generation_id": result.generation_id,
            "candidate_count": result.candidate_count,
            "candidate_sha256": result.candidate_sha256,
            "candidates_path": str(result.candidates_path),
            "quality_report_path": str(result.quality_report_path),
            "ready_for_rdb_import": result.ready_for_rdb_import,
        }
        marker_path = output_root / result.current_marker_path
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=marker_path.parent,
            delete=False,
        ) as temporary:
            json.dump(marker, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, marker_path)


def validate_medication_safety_dataset_version(value: str) -> str:
    normalized = normalize_interaction_name(value)
    if not _SAFE_DATASET_VERSION.fullmatch(normalized):
        raise ValueError("dataset_version은 영문·숫자로 시작하고 영문·숫자·점·밑줄·하이픈만 사용할 수 있습니다.")
    return normalized


def _parse_age_condition(value: str) -> MedicationSafetyConditionCandidate:
    compact = _compact(value)
    match = _AGE_PATTERN.fullmatch(compact)
    if match is None:
        raise _SkipRowError("UNSUPPORTED_AGE_EXPRESSION", value)
    amount = Decimal(match.group("value"))
    unit = match.group("unit")
    if unit == "세":
        condition_kind = SafetyConditionKind.AGE_YEARS
        normalized_amount = amount
        normalized_unit = "year"
    elif unit == "개월":
        if amount % 12 != 0:
            raise _SkipRowError("UNSUPPORTED_AGE_MONTH_UNIT", value)
        condition_kind = SafetyConditionKind.AGE_YEARS
        normalized_amount = amount / 12
        normalized_unit = "year"
    elif unit == "주":
        condition_kind = SafetyConditionKind.AGE_DAYS
        normalized_amount = amount * 7
        normalized_unit = "day"
    else:
        condition_kind = SafetyConditionKind.AGE_DAYS
        normalized_amount = amount
        normalized_unit = "day"
    return MedicationSafetyConditionCandidate(
        condition_group_no=1,
        condition_order=1,
        condition_kind=condition_kind,
        comparison_operator=_OPERATOR_BY_KOREAN[match.group("operator")],
        value_min=normalized_amount,
        unit=normalized_unit,
    )


def _parse_amount(value: str) -> tuple[Decimal, str]:
    compact = _compact(value).replace("|", "").replace(",", "")
    matches = list(_AMOUNT_PATTERN.finditer(compact))
    if not matches:
        raise _SkipRowError("UNSUPPORTED_DOSE_EXPRESSION", value)
    if len(matches) != 1:
        raise _SkipRowError("AMBIGUOUS_DOSE_EXPRESSION", value)
    match = matches[0]
    unit = _DOSE_UNIT_BY_KOREAN[match.group("unit")]
    return Decimal(match.group("amount")), unit


def _numeric_condition(
    kind: SafetyConditionKind,
    amount: Decimal,
    unit: str,
) -> MedicationSafetyConditionCandidate:
    return MedicationSafetyConditionCandidate(
        condition_group_no=1,
        condition_order=1,
        condition_kind=kind,
        comparison_operator=SafetyComparisonOperator.GT,
        value_min=amount,
        unit=unit,
    )


def _text_condition(
    kind: SafetyConditionKind,
    value: str,
    *,
    present: bool = False,
) -> MedicationSafetyConditionCandidate:
    return MedicationSafetyConditionCandidate(
        condition_group_no=1,
        condition_order=1,
        condition_kind=kind,
        comparison_operator=(SafetyComparisonOperator.PRESENT if present else SafetyComparisonOperator.EQ),
        value_text=value,
    )


def _form_and_route_conditions(
    dosage_form: str | None,
    route: str | None,
    *,
    start_order: int,
) -> list[MedicationSafetyConditionCandidate]:
    conditions: list[MedicationSafetyConditionCandidate] = []
    dosage_form_text = _optional_text(dosage_form)
    if dosage_form_text is not None:
        conditions.append(
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=start_order,
                condition_kind=SafetyConditionKind.DOSAGE_FORM,
                comparison_operator=SafetyComparisonOperator.EQ,
                value_text=dosage_form_text,
            )
        )
    route_text = _optional_text(route)
    if route_text is not None:
        conditions.append(
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=start_order + len(conditions),
                condition_kind=SafetyConditionKind.ADMINISTRATION_ROUTE,
                comparison_operator=SafetyComparisonOperator.EQ,
                value_text=route_text,
            )
        )
    return conditions


def _pregnancy_risk(value: str | None) -> InteractionRiskLevel:
    grade = _compact(value or "")
    if grade == "1등급":
        return InteractionRiskLevel.CONTRAINDICATED
    if grade == "2등급":
        return InteractionRiskLevel.HIGH_CAUTION
    if grade == "3등급":
        return InteractionRiskLevel.CAUTION
    raise _SkipRowError("UNSUPPORTED_PREGNANCY_GRADE", value)


def _validate_existing_generation(
    *,
    generation_dir: Path,
    candidate_content: str,
    quality_content: str,
    result: MedicationSafetyStagingResult,
) -> None:
    candidate_path = generation_dir / result.candidates_path.name
    quality_path = generation_dir / result.quality_report_path.name
    try:
        existing_candidates = candidate_path.read_text(encoding="utf-8")
        existing_quality = quality_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"기존 불변 staging 세대가 불완전합니다: {generation_dir}") from error
    if existing_candidates != candidate_content or existing_quality != quality_content:
        raise RuntimeError(f"기존 불변 staging 세대의 내용이 현재 생성 결과와 다릅니다: {generation_dir}")


def _structured_effect_text(
    *,
    document_id: str,
    row: dict[str, str],
    conditions: list[MedicationSafetyConditionCandidate],
) -> str:
    condition = conditions[0]
    value = condition.value_text or str(condition.value_min)
    unit = condition.unit or ""
    return (
        f"{document_id} 구조화 값: {value}{unit}; 원본 행={json.dumps(row, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_date(value: str | None) -> str | None:
    normalized = _compact(value or "")
    if not normalized or normalized == "-":
        return None
    try:
        return datetime.strptime(normalized, "%Y%m%d").date().isoformat()
    except ValueError as error:
        raise _SkipRowError("INVALID_PUBLISHED_DATE", normalized) from error


def _required_row_value(row: dict[str, str], field_name: str) -> str:
    value = _optional_text(row.get(field_name))
    if value is None:
        raise _SkipRowError("MISSING_REQUIRED_VALUE", field_name)
    return value


def _required_text(value: str, field_name: str) -> str:
    normalized = normalize_interaction_name(value)
    if not normalized:
        raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
    return normalized


def _optional_text(value: str | None) -> str | None:
    normalized = normalize_interaction_name(value or "")
    if normalized.casefold() in _MISSING_VALUES:
        return None
    return normalized


def _first_present(*values: str | None) -> str | None:
    for value in values:
        normalized = _optional_text(value)
        if normalized is not None:
            return normalized
    return None


def _normalized_value(value: str | None) -> str:
    return normalize_interaction_name(value or "")


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", normalize_interaction_name(value))
