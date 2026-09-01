import hashlib
import json
from pathlib import Path

import pytest

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionRiskLevel,
)
from ai_worker.schemas.medication_safety import (
    MedicationSafetyConditionCandidate,
    MedicationSafetyRuleCandidate,
    MedicationSafetyRuleType,
    MedicationSafetySourceRecord,
    SafetyComparisonOperator,
    SafetyConditionKind,
)
from scripts.import_medication_safety_staging import (
    MedicationSafetyStagingImportError,
    load_medication_safety_staging_dataset,
)


def build_candidate() -> MedicationSafetyRuleCandidate:
    return MedicationSafetyRuleCandidate(
        dataset_version="medication-safety-v1",
        entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="아세트아미노펜",
            source_code="D000001",
        ),
        rule_type=MedicationSafetyRuleType.DAILY_MAX_DOSE,
        risk_level=InteractionRiskLevel.HIGH_CAUTION,
        guidance_text="1일 최대 투여량을 넘기지 마세요.",
        conditions=[
            MedicationSafetyConditionCandidate(
                condition_group_no=1,
                condition_order=1,
                condition_kind=SafetyConditionKind.DAILY_DOSE,
                comparison_operator=SafetyComparisonOperator.GT,
                value_min=4000,
                unit="mg/day",
            )
        ],
        sources=[
            MedicationSafetySourceRecord(
                source_id="mfds_drug_records",
                document_id="DUR용량주의.csv",
                record_id="1",
                raw_effect_text="아세트아미노펜 4,000mg",
                source_published_at="2026-01-31",
            )
        ],
    )


def write_staging(tmp_path: Path) -> Path:
    root = tmp_path / "processed"
    version = "medication-safety-v1"
    generation = "a" * 64
    generation_root = root / "staging" / version / generation
    generation_root.mkdir(parents=True)
    candidate = build_candidate()
    content = candidate.model_dump_json() + "\n"
    candidate_path = generation_root / "medication_safety_rule_candidates.jsonl"
    candidate_path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    quality_path = generation_root / "medication-safety-staging-quality.json"
    quality_path.write_text(
        json.dumps(
            {
                "dataset_version": version,
                "generation_id": generation,
                "candidate_count": 1,
                "candidate_sha256": digest,
                "candidates_path": str(candidate_path.relative_to(root)),
                "ready_for_rdb_import": False,
            }
        ),
        encoding="utf-8",
    )
    marker_path = root / "staging" / version / "current.json"
    marker_path.write_text(
        json.dumps(
            {
                "dataset_version": version,
                "generation_id": generation,
                "candidate_count": 1,
                "candidate_sha256": digest,
                "candidates_path": str(candidate_path.relative_to(root)),
                "quality_report_path": str(quality_path.relative_to(root)),
                "ready_for_rdb_import": False,
            }
        ),
        encoding="utf-8",
    )
    return marker_path


def test_load_rejects_pending_without_explicit_flag(tmp_path: Path) -> None:
    marker_path = write_staging(tmp_path)

    with pytest.raises(MedicationSafetyStagingImportError, match="--allow-pending"):
        load_medication_safety_staging_dataset(
            marker_path=marker_path,
            allow_pending=False,
        )


def test_load_rejects_candidate_hash_mismatch(tmp_path: Path) -> None:
    marker_path = write_staging(tmp_path)
    candidate_path = marker_path.parent / ("a" * 64) / "medication_safety_rule_candidates.jsonl"
    candidate_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(MedicationSafetyStagingImportError, match="SHA-256"):
        load_medication_safety_staging_dataset(
            marker_path=marker_path,
            allow_pending=True,
        )
