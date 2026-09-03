from pathlib import Path

from scripts.evaluate_medication_search_baseline import (
    load_evaluation_manifest,
)


def test_user_expression_manifest_is_frozen_and_covers_failure_classes() -> None:
    manifest = load_evaluation_manifest(
        Path("data/knowledge/evaluation/user_expression_queries.yaml"),
    )

    assert manifest.frontend_preset is False
    assert manifest.candidate_top_k == 20
    assert manifest.final_top_k == 5
    assert len(manifest.cases) >= 12
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
