from pathlib import Path

from ai_worker.core.config import Config
from ai_worker.schemas.knowledge import KnowledgeVectorDistance
from scripts import evaluate_medication_search_baseline as module

load_evaluation_manifest = module.load_evaluation_manifest


def test_user_expression_manifest_is_frozen_and_covers_failure_classes() -> None:
    manifest = load_evaluation_manifest(
        Path("data/knowledge/evaluation/user_expression_queries.yaml"),
    )

    assert manifest.frontend_preset is False
    assert manifest.schema_version == "medication-search-baseline-v2"
    assert manifest.experiment_goal
    assert manifest.activation_rule
    assert manifest.metric_rationales
    assert manifest.candidate_top_k == 20
    assert manifest.final_top_k == 5
    assert len(manifest.cases) >= 12
    assert all(case.evaluation_rationale for case in manifest.cases)
    assert all(case.evidence_kind is not None for case in manifest.cases)
    assert all(
        set(case.gold_document_rationales) == set(case.expected_document_ids)
        for case in manifest.cases
        if case.expected_document_ids
    )
    categories = {case.expression_category for case in manifest.cases}
    assert {
        "EXACT_PRODUCT",
        "PRODUCT_TYPO",
        "KEYBOARD_TYPO",
        "SPACING_VARIATION",
        "COMMON_NAME",
        "AMBIGUOUS",
        "SHORT_EXPRESSION",
        "OUT_OF_SCOPE",
        "IN_SCOPE_NO_EVIDENCE",
        "DRUG_DRUG",
        "DRUG_SUPPLEMENT",
        "SUPPLEMENT_SUPPLEMENT",
        "DRUG_FOOD",
    }.issubset(categories)


def test_v3_manifest_is_fixed_to_21_cases_and_tracks_historical_outcomes() -> None:
    manifest = load_evaluation_manifest(
        Path("data/knowledge/evaluation/user_expression_queries_v3.yaml"),
    )

    assert manifest.schema_version == "medication-search-baseline-v3"
    assert len(manifest.cases) == 21
    assert sum(case.phase == "ACTIVE_PHASE" for case in manifest.cases) > 0
    assert all(case.evaluation_rationale for case in manifest.cases)
    assert all(case.historical_outcome is not None for case in manifest.cases)
    assert sum(case.historical_outcome == "PASS" for case in manifest.cases) == 11
    assert sum(case.historical_outcome == "PARTIAL" for case in manifest.cases) == 4
    assert sum(case.historical_outcome == "FAIL" for case in manifest.cases) == 6


def test_evaluation_vector_store_uses_runtime_dot_distance() -> None:
    settings = Config(
        _env_file=None,
        KNOWLEDGE_VECTOR_DISTANCE=KnowledgeVectorDistance.DOT,
        OPENAI_EMBEDDING_DIMENSIONS=1536,
    )

    vector_store = module.build_evaluation_vector_store(
        settings=settings,
        qdrant_client=object(),
        collection_name="medication_knowledge_full_v5",
    )

    assert vector_store._distance == KnowledgeVectorDistance.DOT
