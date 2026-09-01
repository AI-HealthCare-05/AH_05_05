import csv
import json
from pathlib import Path

import pytest

from ai_worker.schemas.medication_safety import (
    MedicationSafetyRuleCandidate,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)
from ai_worker.services.medication_safety_staging_service import (
    MedicationSafetyStagingService,
)

DUR_FIELDS = [
    "DUR일련번호",
    "DUR유형",
    "DUR성분코드",
    "DUR성분명",
    "DUR성분명영문",
    "고시일자",
    "금기내용",
    "제형",
    "연령기준",
    "최대투여기간",
    "1일최대용량",
    "등급",
    "비고",
    "상태",
]

DAILY_MAX_FIELDS = [
    "성분코드",
    "성분명(한글)",
    "성분명(영문)",
    "제형코드",
    "제형명",
    "투여경로",
    "투여단위",
    "1일최대투여량",
]


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def dur_row(
    record_id: str,
    dur_type: str,
    *,
    code: str,
    name: str,
    effect: str = "-",
    dosage_form: str = "정제",
    age: str = "-",
    duration: str = "-",
    daily_dose: str = "-",
    grade: str = "-",
    note: str = "-",
    status: str = "정상",
) -> dict[str, str]:
    return {
        "DUR일련번호": record_id,
        "DUR유형": dur_type,
        "DUR성분코드": code,
        "DUR성분명": name,
        "DUR성분명영문": "",
        "고시일자": "20260131",
        "금기내용": effect,
        "제형": dosage_form,
        "연령기준": age,
        "최대투여기간": duration,
        "1일최대용량": daily_dose,
        "등급": grade,
        "비고": note,
        "상태": status,
    }


def build_input_files(tmp_path: Path) -> list[Path]:
    fixtures = {
        "DUR임부금기.csv": [
            dur_row(
                "p-1",
                "임부금기",
                code="D000149",
                name="아카보즈",
                effect="임부에 대한 안전성 미확립",
                grade="2등급",
            )
        ],
        "DUR특정연령대금기.csv": [
            dur_row(
                "a-1",
                "특정연령대금기",
                code="D000025",
                name="시클로펜톨레이트",
                effect="1세 미만 투여 금기",
                age="1세미만",
            )
        ],
        "DUR노인주의.csv": [
            dur_row(
                "e-1",
                "노인주의",
                code="D000020",
                name="블로난세린",
                effect="고령자는 신중히 투여",
            )
        ],
        "DUR용량주의.csv": [
            dur_row(
                "d-1",
                "용량주의",
                code="D000010",
                name="반코마이신염산염",
                effect="1일 최대 용량 주의",
                daily_dose="4|000밀리그램",
            )
        ],
        "DUR투여기간주의.csv": [
            dur_row(
                "t-1",
                "투여기간주의",
                code="D000078",
                name="그라니세트론",
                duration="7일",
            )
        ],
        "DUR첨가제주의.csv": [
            dur_row(
                "x-1",
                "첨가제주의",
                code="D001041",
                name="유당",
                effect="유당 관련 유전 질환이 있는 환자에게 투여하면 안 된다.",
                dosage_form="-",
                note="유당(경구제 및 주사제에 한함)",
            )
        ],
    }
    paths: list[Path] = []
    for name, rows in fixtures.items():
        path = tmp_path / name
        write_csv(path, DUR_FIELDS, rows)
        paths.append(path)

    daily_path = tmp_path / "1일최대투여량.csv"
    write_csv(
        daily_path,
        DAILY_MAX_FIELDS,
        [
            {
                "성분코드": "M222875",
                "성분명(한글)": "암로디핀베실산염",
                "성분명(영문)": "AmlodipineBesylate",
                "제형코드": "010000",
                "제형명": "정제",
                "투여경로": "경구",
                "투여단위": "정",
                "1일최대투여량": "4",
            }
        ],
    )
    paths.append(daily_path)
    return paths


def load_candidates(
    output_root: Path,
    relative_path: Path,
) -> list[MedicationSafetyRuleCandidate]:
    return [
        MedicationSafetyRuleCandidate.model_validate_json(line)
        for line in (output_root / relative_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_build_converts_all_seven_source_types(tmp_path: Path) -> None:
    output_root = tmp_path / "processed"
    result = MedicationSafetyStagingService().build(
        input_paths=build_input_files(tmp_path),
        output_root=output_root,
        dataset_version="medication-safety-2026-09",
    )

    assert result.input_row_count == 7
    assert result.accepted_row_count == 7
    assert result.candidate_count == 7
    assert result.skipped_rows == []
    candidates = load_candidates(output_root, result.candidates_path)
    by_type = {candidate.rule_type: candidate for candidate in candidates}
    assert set(by_type) == set(MedicationSafetyRuleType)

    pregnancy = by_type[MedicationSafetyRuleType.PREGNANCY_CONTRAINDICATION]
    assert pregnancy.conditions[0].condition_kind == SafetyConditionKind.PREGNANCY_STATUS
    assert pregnancy.conditions[0].value_text == "PREGNANT"

    age = by_type[MedicationSafetyRuleType.AGE_CONTRAINDICATION]
    assert age.conditions[0].comparison_operator == SafetyComparisonOperator.LT
    assert age.conditions[0].value_min == 1

    dose = by_type[MedicationSafetyRuleType.DOSE_CAUTION]
    assert dose.conditions[0].value_min == 4000
    assert dose.conditions[0].unit == "mg/day"

    duration = by_type[MedicationSafetyRuleType.DURATION_CAUTION]
    assert duration.conditions[0].value_min == 7

    daily_max = by_type[MedicationSafetyRuleType.DAILY_MAX_DOSE]
    assert daily_max.conditions[0].unit == "tablet/day"
    assert len(daily_max.conditions) == 3

    excipient = by_type[MedicationSafetyRuleType.EXCIPIENT_CAUTION]
    assert excipient.conditions[0].value_text == "유당"


def test_build_skips_unsafe_age_conversion_and_inactive_rows(
    tmp_path: Path,
) -> None:
    paths = build_input_files(tmp_path)
    age_path = next(path for path in paths if path.name == "DUR특정연령대금기.csv")
    write_csv(
        age_path,
        DUR_FIELDS,
        [
            dur_row(
                "a-1",
                "특정연령대금기",
                code="D1",
                name="성분1",
                age="6개월미만",
            ),
            dur_row(
                "a-2",
                "특정연령대금기",
                code="D2",
                name="성분2",
                age="12개월미만",
            ),
            dur_row(
                "a-3",
                "특정연령대금기",
                code="D3",
                name="성분3",
                age="18세미만",
                status="삭제",
            ),
        ],
    )

    result = MedicationSafetyStagingService().build(
        input_paths=paths,
        output_root=tmp_path / "processed",
        dataset_version="medication-safety-2026-09",
    )

    assert result.accepted_row_count == 7
    assert result.skipped_reason_counts == {
        "INACTIVE_STATUS": 1,
        "UNSUPPORTED_AGE_MONTH_UNIT": 1,
    }
    candidate = next(
        item
        for item in load_candidates(tmp_path / "processed", result.candidates_path)
        if item.rule_type == MedicationSafetyRuleType.AGE_CONTRAINDICATION
    )
    assert candidate.conditions[0].condition_kind == SafetyConditionKind.AGE_YEARS
    assert candidate.conditions[0].value_min == 1


def test_build_is_deterministic_and_records_quality_hash(tmp_path: Path) -> None:
    paths = build_input_files(tmp_path)
    output_root = tmp_path / "processed"
    service = MedicationSafetyStagingService()

    first = service.build(
        input_paths=paths,
        output_root=output_root,
        dataset_version="medication-safety-2026-09",
    )
    second = service.build(
        input_paths=list(reversed(paths)),
        output_root=output_root,
        dataset_version="medication-safety-2026-09",
    )

    assert first.generation_id == second.generation_id
    assert first.candidate_sha256 == second.candidate_sha256
    quality = json.loads((output_root / first.quality_report_path).read_text(encoding="utf-8"))
    assert quality["candidate_sha256"] == first.candidate_sha256
    assert quality["ready_for_rdb_import"] is False


def test_build_requires_exactly_one_of_each_supported_source(tmp_path: Path) -> None:
    paths = build_input_files(tmp_path)
    service = MedicationSafetyStagingService()

    with pytest.raises(ValueError, match="7종 CSV"):
        service.build(
            input_paths=paths[:-1],
            output_root=tmp_path / "missing",
            dataset_version="medication-safety-2026-09",
        )

    with pytest.raises(ValueError, match="7종 CSV"):
        service.build(
            input_paths=[*paths, paths[0]],
            output_root=tmp_path / "duplicate",
            dataset_version="medication-safety-2026-09",
        )


def test_build_skips_ambiguous_dose_and_unknown_pregnancy_grade(
    tmp_path: Path,
) -> None:
    paths = build_input_files(tmp_path)
    dose_path = next(path for path in paths if path.name == "DUR용량주의.csv")
    pregnancy_path = next(path for path in paths if path.name == "DUR임부금기.csv")
    write_csv(
        dose_path,
        DUR_FIELDS,
        [
            dur_row(
                "d-ambiguous",
                "용량주의",
                code="D100",
                name="부프로피온염산염",
                daily_dose="부프로피온염산염360밀리그램/날트렉손염산염32밀리그램",
            )
        ],
    )
    write_csv(
        pregnancy_path,
        DUR_FIELDS,
        [
            dur_row(
                "p-unknown",
                "임부금기",
                code="D200",
                name="등급미상성분",
                grade="-",
            )
        ],
    )

    result = MedicationSafetyStagingService().build(
        input_paths=paths,
        output_root=tmp_path / "processed",
        dataset_version="medication-safety-2026-09",
    )

    assert result.skipped_reason_counts == {
        "AMBIGUOUS_DOSE_EXPRESSION": 1,
        "UNSUPPORTED_PREGNANCY_GRADE": 1,
    }
    assert result.accepted_row_count == 5


def test_failed_generation_write_does_not_publish_partial_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = build_input_files(tmp_path)
    output_root = tmp_path / "processed"
    original_write_text = Path.write_text

    def fail_quality_write(path: Path, data: str, **kwargs) -> int:
        if path.name == "medication-safety-staging-quality.json":
            raise OSError("simulated write failure")
        return original_write_text(path, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_quality_write)

    with pytest.raises(OSError, match="simulated write failure"):
        MedicationSafetyStagingService().build(
            input_paths=paths,
            output_root=output_root,
            dataset_version="medication-safety-2026-09",
        )

    generation_dirs = list((output_root / "staging" / "medication-safety-2026-09").glob("[0-9a-f]*"))
    assert generation_dirs == []
    assert not (output_root / "staging" / "medication-safety-2026-09" / "current.json").exists()
