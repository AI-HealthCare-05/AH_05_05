"""Safe v3 orchestration from General OCR to grounded medication review data."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from app.services.medication_ocr_v3.domain.grounding import (
    EvidenceCatalog,
    GroundingSelection,
    SemanticGroundingSelection,
)
from app.services.medication_ocr_v3.domain.models import OcrErrorCode, OcrProviderError, OcrResult
from app.services.medication_ocr_v3.pipeline.deterministic_grounding import (
    DeterministicGroundingPlan,
    canonicalize_deterministic_selection,
    materialize_deterministic_grounding,
    plan_deterministic_grounding,
)
from app.services.medication_ocr_v3.pipeline.evidence_catalog import build_evidence_catalog
from app.services.medication_ocr_v3.pipeline.grounding import GroundedField, GroundedResult, GroundingIssue, seoul_today
from app.services.medication_ocr_v3.pipeline.hospital_name import HospitalNameExtraction, extract_hospital_name
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationRow,
    MedicationRowsResult,
    materialize_medication_rows,
)
from app.services.medication_ocr_v3.pipeline.ocr_layout import OcrLayoutResult, build_ocr_layout
from app.services.medication_ocr_v3.pipeline.review_projection import build_project_review
from app.services.medication_ocr_v3.pipeline.semantic_catalog import build_semantic_evidence_catalog
from app.services.medication_ocr_v3.pipeline.semantic_grounding import materialize_semantic_review
from app.services.medication_ocr_v3.providers.openai_grounded import (
    PROMPT_VERSION,
    GroundedStructurer,
    LlmErrorCode,
    LlmProviderError,
)

CONTRACT_VERSION = "v3"
GROUNDING_SCHEMA_VERSION = "medication_grounding_v3"
DEFAULT_MODEL_VERSION = "gpt-5.6-terra"

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.md"


class GeneralOcrProvider(Protocol):
    """The narrow General OCR surface owned by the app lifecycle."""

    async def recognize(self, processed_jpeg: bytes) -> OcrResult: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    status: str
    elapsed_ms: int
    call_count: int
    code: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "elapsedMs": self.elapsed_ms,
            "callCount": self.call_count,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class AnalyzePipelineFailure:
    code: OcrErrorCode
    status_code: int
    ocr_elapsed_ms: int = 0
    stages: tuple[StageResult, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalyzePipelineCancellation:
    stages: tuple[StageResult, ...]


@dataclass(frozen=True, slots=True)
class AnalyzePipelineResult:
    """Completed OCR analysis with structure time across candidate, resolve, LLM, and validate."""

    ocr_result: OcrResult
    layout: OcrLayoutResult
    medication_rows: MedicationRowsResult
    ocr_elapsed_ms: int = 0
    structure_elapsed_ms: int = 0
    catalog: EvidenceCatalog | None = None
    grounded: GroundedResult | None = None
    project_review: dict[str, object] | None = None
    issues: tuple[dict[str, object], ...] | None = None
    stages: tuple[StageResult, ...] = ()
    diagnostics: dict[str, object] | None = None

    @property
    def analysis_state(self) -> str:
        if (
            self.project_review is not None
            and not self.project_review.get("medications")
            and any(stage.status == "failed" for stage in self.stages)
        ):
            return "FAILED"
        project_review = self.project_review or build_project_review(self.medication_rows)
        issues = self.issues or tuple(issue.as_dict() for issue in self.medication_rows.issues)
        medications = project_review.get("medications")
        if (
            not isinstance(medications, list)
            or not medications
            or issues
            or any(row.issues for row in self.medication_rows.medications)
        ):
            return "COMPLETED_WITH_ISSUES"
        return "COMPLETED"

    def result_payload(self) -> dict[str, object]:
        ocr_payload = self.ocr_result.as_dict()
        layout_payload = self.layout.as_dict()
        project_review = self.project_review or build_project_review(self.medication_rows)
        issues = self.issues or tuple(issue.as_dict() for issue in self.medication_rows.issues)
        return {
            "analysisState": self.analysis_state,
            "ocr": {
                "coordinateSpace": "processed",
                "blocks": ocr_payload["blocks"],
                "lines": layout_payload["lines"],
            },
            "issues": list(issues),
            "projectReview": project_review,
            "diagnostics": self.diagnostics or {},
        }


async def analyze_processed_image(
    provider: GeneralOcrProvider,
    processed_jpeg: bytes,
    structurer: GroundedStructurer | None = None,
    is_cancelled: Callable[[], Awaitable[bool]] | None = None,
) -> AnalyzePipelineResult | AnalyzePipelineFailure | AnalyzePipelineCancellation:
    """Run the OCR, candidate, resolve, LLM, and validate stages once each when needed."""

    ocr_started = time.perf_counter()
    try:
        ocr_result = await provider.recognize(processed_jpeg)
    except OcrProviderError as error:
        ocr_elapsed_ms = _elapsed_ms(ocr_started)
        return AnalyzePipelineFailure(
            code=error.code,
            status_code=error.status_code,
            ocr_elapsed_ms=ocr_elapsed_ms,
            stages=(
                StageResult("ocr", "failed", ocr_elapsed_ms, 1, error.code.value),
                StageResult("candidate", "skipped", 0, 0, "UPSTREAM_FAILED"),
                StageResult("resolve", "skipped", 0, 0, "UPSTREAM_FAILED"),
                StageResult("llm", "skipped", 0, 0, "UPSTREAM_FAILED"),
                StageResult("validate", "skipped", 0, 0, "UPSTREAM_FAILED"),
            ),
        )
    ocr_stage = StageResult("ocr", "succeeded", _elapsed_ms(ocr_started), 1)

    if is_cancelled is not None and await is_cancelled():
        return AnalyzePipelineCancellation(
            stages=(
                ocr_stage,
                *(
                    StageResult(name, "skipped", 0, 0, "REQUEST_CANCELLED")
                    for name in ("candidate", "resolve", "llm", "validate")
                ),
            )
        )
    if not ocr_result.blocks:
        return _stopped_analysis(
            ocr_result,
            (StageResult("ocr", "failed", ocr_stage.elapsed_ms, 1, "NO_OCR_BLOCKS"),),
            ("candidate", "resolve", "llm", "validate"),
        )

    candidate_started = time.perf_counter()
    layout = build_ocr_layout(ocr_result)
    hospital_name = extract_hospital_name(ocr_result, layout)
    medication_rows = materialize_medication_rows(layout)
    original_catalog = build_evidence_catalog(ocr_result, layout, medication_rows)
    semantic = getattr(structurer, "review_mode", "legacy") == "semantic"
    catalog = (
        build_semantic_evidence_catalog(ocr_result, layout, medication_rows, original_catalog)
        if semantic
        else original_catalog
    )
    candidate_stage = StageResult("candidate", "succeeded", _elapsed_ms(candidate_started), 0)

    if not medication_rows.medications or not catalog.rows:
        cause = next(
            (
                issue.code.value
                for issue in medication_rows.issues
                if issue.code.value in {"AMBIGUOUS_MEDICATION_TABLE", "TABLE_NOT_FOUND"}
            ),
            "NO_EVIDENCE_ROWS",
        )
        return _stopped_analysis(
            ocr_result,
            (ocr_stage, StageResult("candidate", "failed", candidate_stage.elapsed_ms, 0, cause)),
            ("resolve", "llm", "validate"),
            layout=layout,
            medication_rows=medication_rows,
        )
    if medication_rows.issues or any(row.issues for row in medication_rows.medications):
        candidate_stage = StageResult("candidate", "succeeded", candidate_stage.elapsed_ms, 0, "COMPLETED_WITH_ISSUES")

    if is_cancelled is not None and await is_cancelled():
        return AnalyzePipelineCancellation(
            stages=(
                ocr_stage,
                candidate_stage,
                StageResult("resolve", "skipped", 0, 0, "REQUEST_CANCELLED"),
                StageResult("llm", "skipped", 0, 0, "REQUEST_CANCELLED"),
                StageResult("validate", "skipped", 0, 0, "REQUEST_CANCELLED"),
            )
        )

    resolve_started = time.perf_counter()
    run_today = seoul_today()
    plan = plan_deterministic_grounding(
        original_catalog,
        medication_rows,
        today=run_today,
    )
    selection = _empty_selection()
    pipeline_issue_code: str | None = None
    grounding_required = bool(catalog.rows) if semantic else plan.ambiguity_required
    llm_skip_code: str | None = None
    should_call_llm = False
    if not (catalog.rows if semantic else plan.deterministic_row_ids):
        return _stopped_analysis(
            ocr_result,
            (
                ocr_stage,
                candidate_stage,
                StageResult("resolve", "failed", _elapsed_ms(resolve_started), 0, "NO_EVIDENCE_ROWS"),
            ),
            ("llm", "validate"),
            layout=layout,
            medication_rows=medication_rows,
        )
    if not grounding_required:
        llm_skip_code = "DETERMINISTIC_SUFFICIENT"
    elif structurer is None:
        pipeline_issue_code = "LLM_UNAVAILABLE"
        llm_skip_code = pipeline_issue_code
    else:
        should_call_llm = True

    resolve_stage = StageResult("resolve", "succeeded", _elapsed_ms(resolve_started), 0)
    if not should_call_llm:
        llm_stage = StageResult("llm", "skipped", 0, 0, llm_skip_code)
    else:
        llm_started = time.perf_counter()
        try:
            selection = await structurer.select(catalog if semantic else _ambiguity_catalog(catalog, plan))
            expected_model = SemanticGroundingSelection if semantic else GroundingSelection
            if not isinstance(selection, expected_model):
                raise LlmProviderError(LlmErrorCode.LLM_SCHEMA_INVALID, 502)
        except LlmProviderError as error:
            pipeline_issue_code = error.code.value
            llm_stage = StageResult("llm", "failed", _elapsed_ms(llm_started), 1, pipeline_issue_code)
        else:
            llm_stage = StageResult("llm", "succeeded", _elapsed_ms(llm_started), 1)
    validate_started = time.perf_counter()
    canonical = canonicalize_deterministic_selection(
        original_catalog,
        medication_rows,
        selection if isinstance(selection, GroundingSelection) else _empty_selection(),
        today=run_today,
    )
    grounded = materialize_deterministic_grounding(
        original_catalog,
        medication_rows,
        canonical,
        today=run_today,
    )
    if semantic and llm_stage.status == "succeeded" and isinstance(selection, SemanticGroundingSelection):
        medication_rows, grounded = materialize_semantic_review(catalog, medication_rows, grounded, selection)
    project_review = build_project_review(medication_rows, grounded, hospital_name)
    issues = _result_issues(medication_rows, pipeline_issue_code, grounded, hospital_name)
    if llm_stage.status == "succeeded" and _missing_expected_medication_output(
        medication_rows,
        project_review,
    ):
        issues = (*issues, _pipeline_issue("LLM_GROUNDING_INCOMPLETE"))
    diagnostics: dict[str, object] = {
        "fieldEvidence": _field_evidence(
            project_review,
            medication_rows,
            catalog,
            grounded,
            hospital_name,
        ),
        "groundingIssues": [issue.as_dict() for issue in grounded.issues],
        "llm": {
            "ambiguityRequired": plan.ambiguity_required,
            "mode": "semantic" if semantic else "legacy",
            "reviewRequired": grounding_required,
        },
        "versions": _versions(structurer),
    }
    if not project_review.get("medications"):
        validate_stage = StageResult("validate", "failed", _elapsed_ms(validate_started), 0, "NO_VALID_MEDICATION_ROWS")
    else:
        has_issues = bool(issues or any(row.issues for row in medication_rows.medications))
        validate_stage = StageResult(
            "validate",
            "succeeded",
            _elapsed_ms(validate_started),
            0,
            "COMPLETED_WITH_ISSUES" if has_issues else None,
        )
    return AnalyzePipelineResult(
        ocr_result=ocr_result,
        layout=layout,
        medication_rows=medication_rows,
        ocr_elapsed_ms=ocr_stage.elapsed_ms,
        structure_elapsed_ms=sum(
            stage.elapsed_ms for stage in (candidate_stage, resolve_stage, llm_stage, validate_stage)
        ),
        catalog=catalog,
        grounded=grounded,
        project_review=project_review,
        issues=issues,
        stages=(ocr_stage, candidate_stage, resolve_stage, llm_stage, validate_stage),
        diagnostics=diagnostics,
    )


def _stopped_analysis(
    ocr_result: OcrResult,
    completed: tuple[StageResult, ...],
    remaining: tuple[str, ...],
    *,
    layout: OcrLayoutResult | None = None,
    medication_rows: MedicationRowsResult | None = None,
) -> AnalyzePipelineResult:
    """Preserve the cause at its origin; do not run dependent work on unusable input."""
    return AnalyzePipelineResult(
        ocr_result=ocr_result,
        layout=layout if layout is not None else OcrLayoutResult((), (), ()),
        medication_rows=medication_rows if medication_rows is not None else MedicationRowsResult(None, (), ()),
        ocr_elapsed_ms=completed[0].elapsed_ms,
        structure_elapsed_ms=sum(stage.elapsed_ms for stage in completed[1:]),
        project_review={"fields": {}, "medications": [], "lowConfidenceCount": 0},
        issues=(_pipeline_issue(completed[-1].code or "EXTRACTION_FAILED"),),
        stages=(*completed, *(StageResult(name, "skipped", 0, 0, "UPSTREAM_FAILED") for name in remaining)),
    )


def _empty_selection() -> GroundingSelection:
    return GroundingSelection(dispensed_date_block_ids=[], medications=[])


def _ambiguity_catalog(
    catalog: EvidenceCatalog,
    plan: DeterministicGroundingPlan,
) -> EvidenceCatalog:
    rows = tuple(row for row in catalog.rows if row.row_id in plan.ambiguous_strength_row_ids)
    relevant_ids = {block_id for row in rows for block_id in row.block_ids}
    date_candidates = catalog.date_candidates if plan.ambiguous_date else ()
    relevant_ids.update(block.block_id for block in date_candidates)
    return EvidenceCatalog(
        blocks=tuple(block for block in catalog.blocks if block.block_id in relevant_ids),
        date_candidates=date_candidates,
        rows=rows,
        schema_version=catalog.schema_version,
    )


def _result_issues(
    medication_rows: MedicationRowsResult,
    pipeline_issue_code: str | None,
    grounded: GroundedResult,
    hospital_name: HospitalNameExtraction,
) -> tuple[dict[str, object], ...]:
    issues = [issue.as_dict() for issue in medication_rows.issues]
    if pipeline_issue_code is not None:
        issues.append(_pipeline_issue(pipeline_issue_code))
    issues.extend(issue.as_dict() for issue in grounded.issues)
    issues.extend(
        {
            "code": issue.value,
            "rowId": None,
            "field": "hospitalName",
            "blockIds": list(hospital_name.block_ids),
        }
        for issue in hospital_name.issues
    )
    dispensed_date = grounded.dispensed_date
    if isinstance(dispensed_date.value, str) and dispensed_date.value and not _is_iso_date(dispensed_date.value):
        issues.append(
            {
                "code": "INVALID_FIELD_VALUE",
                "rowId": None,
                "field": "dispensedDate",
                "blockIds": list(dispensed_date.block_ids),
            }
        )
    return tuple(issues)


def _is_iso_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _missing_expected_medication_output(
    medication_rows: MedicationRowsResult,
    project_review: dict[str, object],
) -> bool:
    medications = project_review.get("medications")
    if not isinstance(medications, list):
        return bool(medication_rows.medications)
    if len(medications) != len(medication_rows.medications):
        return True
    for row, medication in zip(medication_rows.medications, medications, strict=True):
        if not isinstance(medication, dict):
            return True
        if row.name and medication.get("name") != row.name:
            return True
    return False


def _pipeline_issue(code: str) -> dict[str, object]:
    return {"code": code, "blockIds": []}


def _field_evidence(
    project_review: dict[str, object],
    medication_rows: MedicationRowsResult,
    catalog: EvidenceCatalog,
    grounded: GroundedResult,
    hospital_name: HospitalNameExtraction,
) -> dict[str, object]:
    public_medications = project_review.get("medications")
    if not isinstance(public_medications, list):
        public_medications = []
    grounded_by_row_id = {medication.row_id: medication for medication in grounded.medications}
    medications: list[dict[str, object]] = []
    for public in public_medications:
        if not isinstance(public, dict):
            continue
        temp_id = public.get("tempId")
        if not isinstance(temp_id, str) or not temp_id.startswith("med-"):
            continue
        try:
            source_index = int(temp_id.removeprefix("med-"))
        except ValueError:
            continue
        if not 1 <= source_index <= len(medication_rows.medications):
            continue
        row = medication_rows.medications[source_index - 1]
        row_id = _catalog_row_id(row, catalog)
        grounded_medication = grounded_by_row_id.get(row_id) if row_id is not None else None
        evidence: dict[str, object] = {
            "tempId": temp_id,
            "name": _deterministic_evidence(row.fields.name),
            "strength": _grounded_evidence(grounded_medication.strength if grounded_medication is not None else None),
            "doseQuantity": _deterministic_evidence(row.fields.dose_quantity),
            "timesPerDay": _deterministic_evidence(row.fields.times_per_day),
            "days": _deterministic_evidence(row.fields.days),
        }
        if row_id is not None:
            _merge_issue_codes(evidence, row_id, grounded.issues)
        medications.append(evidence)
    return {
        "hospitalName": _hospital_name_evidence(hospital_name),
        "dispensedDate": _grounded_evidence(grounded.dispensed_date),
        "medications": medications,
    }


def _hospital_name_evidence(field: HospitalNameExtraction) -> dict[str, object]:
    issues = [issue.value for issue in field.issues]
    if field.value in (None, "") and not issues:
        issues.append("MISSING_FIELD")
    return {
        "blockIds": list(field.block_ids),
        "bbox": field.bbox.as_dict() if field.bbox is not None else None,
        "confidence": _confidence_tier(field.confidence),
        "issues": issues,
    }


def _merge_issue_codes(
    medication_evidence: dict[str, object],
    row_id: str,
    issues: tuple[GroundingIssue, ...],
) -> None:
    public_fields = {
        "name": "name",
        "strength": "strength",
        "doseQuantity": "doseQuantity",
        "timesPerDay": "timesPerDay",
        "days": "days",
    }
    for issue in issues:
        public_field = public_fields.get(issue.field)
        if issue.row_id != row_id or public_field is None:
            continue
        field_evidence = medication_evidence.get(public_field)
        if not isinstance(field_evidence, dict):
            continue
        issue_codes = field_evidence.get("issues")
        if not isinstance(issue_codes, list):
            continue
        field_evidence["issues"] = list(dict.fromkeys([*issue_codes, issue.code.value]))


def _catalog_row_id(
    medication: MedicationRow,
    catalog: EvidenceCatalog,
) -> str | None:
    name_block_ids = set(medication.fields.name.block_ids)
    matches = tuple(row.row_id for row in catalog.rows if name_block_ids.intersection(row.block_ids))
    if len(matches) == 1:
        return matches[0]
    return None


def _grounded_evidence(field: GroundedField | None) -> dict[str, object]:
    if field is None:
        return _empty_field_evidence()
    issues = [issue.value for issue in field.issues]
    if field.value in (None, "") and not issues:
        issues.append("MISSING_FIELD")
    return {
        "blockIds": list(field.block_ids),
        "bbox": field.bbox.as_dict() if field.bbox is not None else None,
        "confidence": _confidence_tier(field.confidence),
        "issues": issues,
    }


def _deterministic_evidence(field: MedicationField) -> dict[str, object]:
    issues = [issue.value for issue in field.issues]
    if field.value in (None, "") and not issues:
        issues.append("MISSING_FIELD")
    return {
        "blockIds": list(field.block_ids),
        "bbox": field.bbox.as_dict() if field.bbox is not None else None,
        "confidence": _confidence_tier(field.confidence),
        "issues": issues,
    }


def _empty_field_evidence() -> dict[str, object]:
    return {
        "blockIds": [],
        "bbox": None,
        "confidence": "low",
        "issues": ["MISSING_FIELD"],
    }


def _confidence_tier(confidence: float | None) -> str:
    if confidence is None or confidence < 0.70:
        return "low"
    if confidence < 0.90:
        return "medium"
    return "high"


def _versions(structurer: GroundedStructurer | None) -> dict[str, dict[str, str]]:
    model_version = _model_version(structurer)
    prompt_version = getattr(structurer, "prompt_version", PROMPT_VERSION)
    schema_version = getattr(structurer, "schema_version", GROUNDING_SCHEMA_VERSION)
    selection_model = (
        SemanticGroundingSelection if getattr(structurer, "review_mode", "legacy") == "semantic" else GroundingSelection
    )
    return {
        "contract": _version(CONTRACT_VERSION, f"medication-ocr-api:{CONTRACT_VERSION}"),
        "prompt": _version(prompt_version, _prompt_source(prompt_version)),
        "schema": _version(
            schema_version,
            json.dumps(
                selection_model.model_json_schema(by_alias=True),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
        "model": _version(model_version, model_version),
    }


def _model_version(structurer: GroundedStructurer | None) -> str:
    if structurer is None:
        return DEFAULT_MODEL_VERSION
    value = getattr(structurer, "model_version", None)
    if isinstance(value, str) and value:
        return value
    return DEFAULT_MODEL_VERSION


def _prompt_source(prompt_version: str = PROMPT_VERSION) -> str:
    try:
        return _PROMPT_PATH.with_name(f"{prompt_version}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return prompt_version


def _version(name: str, source: str) -> dict[str, str]:
    return {
        "name": name,
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
