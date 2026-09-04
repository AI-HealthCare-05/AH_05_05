import pytest
from pydantic import ValidationError

from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineManifest,
)

METRIC_RATIONALES = {
    "recall_at_20": "관련 문서가 후보군에 들어오는지 확인합니다.",
    "hit_at_5": "최종 답변에 사용할 상위 근거를 확인합니다.",
    "mrr": "첫 정답 문서가 얼마나 앞에 배치되는지 확인합니다.",
    "source_accuracy": "선택된 출처가 골드 문서인지 확인합니다.",
    "evidence_coverage_rate": "요청 항목별 근거가 모두 있는지 확인합니다.",
    "wrong_target_mixing_count": "다른 약과 성분의 혼입을 차단합니다.",
    "duplicate_retrieval_rate": "같은 근거의 반복 노출을 확인합니다.",
    "search_p95_ms": "정확도를 훼손하지 않는 범위에서 지연을 감시합니다.",
}


def test_v2_manifest_requires_experiment_and_case_rationales() -> None:
    with pytest.raises(ValidationError, match="실험 목적"):
        MedicationSearchBaselineManifest.model_validate(
            {
                "schema_version": "medication-search-baseline-v2",
                "dataset_version": "knowledge-full-v2-interaction-metadata",
                "collection_name": "medication_knowledge_full_v2",
                "cases": [
                    {
                        "query_id": "calcium-iron",
                        "question": "칼슘과 철분을 같이 먹어도 되나요?",
                        "expected_scope": "IN_SCOPE",
                        "expected_resolution_status": "UNCHANGED",
                    }
                ],
            }
        )


def test_v2_manifest_requires_reason_for_every_gold_document() -> None:
    with pytest.raises(ValidationError, match="골드 문서 선정 근거"):
        MedicationSearchBaselineManifest.model_validate(
            {
                "schema_version": "medication-search-baseline-v2",
                "dataset_version": "knowledge-full-v2-interaction-metadata",
                "collection_name": "medication_knowledge_full_v2",
                "experiment_goal": "Dense와 Hybrid의 검색 정확도를 비교합니다.",
                "activation_rule": "정확도가 개선되고 안전 지표가 악화되지 않을 때만 채택합니다.",
                "metric_rationales": METRIC_RATIONALES,
                "cases": [
                    {
                        "query_id": "calcium-iron",
                        "question": "칼슘과 철분을 같이 먹어도 되나요?",
                        "expected_scope": "IN_SCOPE",
                        "expected_resolution_status": "UNCHANGED",
                        "evidence_kind": "QDRANT_GOLD",
                        "evaluation_rationale": "영양제 간 상호작용 검색을 검증합니다.",
                        "expected_document_ids": ["calcium-iron-paper"],
                    }
                ],
            }
        )


def test_v2_manifest_accepts_explained_gold_document_contract() -> None:
    manifest = MedicationSearchBaselineManifest.model_validate(
        {
            "schema_version": "medication-search-baseline-v2",
            "dataset_version": "knowledge-full-v2-interaction-metadata",
            "collection_name": "medication_knowledge_full_v2",
            "experiment_goal": "Dense와 Hybrid의 검색 정확도를 비교합니다.",
            "activation_rule": "정확도가 개선되고 안전 지표가 악화되지 않을 때만 채택합니다.",
            "metric_rationales": METRIC_RATIONALES,
            "cases": [
                {
                    "query_id": "calcium-iron",
                    "question": "칼슘과 철분을 같이 먹어도 되나요?",
                    "expected_scope": "IN_SCOPE",
                    "expected_resolution_status": "UNCHANGED",
                    "evidence_kind": "QDRANT_GOLD",
                    "evaluation_rationale": "영양제 간 상호작용 검색을 검증합니다.",
                    "expected_document_ids": ["calcium-iron-paper"],
                    "gold_document_rationales": {
                        "calcium-iron-paper": "칼슘과 철분을 직접 함께 다룬 사람 대상 연구입니다."
                    },
                }
            ],
        }
    )

    assert manifest.cases[0].gold_document_rationales == {
        "calcium-iron-paper": "칼슘과 철분을 직접 함께 다룬 사람 대상 연구입니다."
    }
