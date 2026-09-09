from collections import Counter
from pathlib import Path

import yaml

from ai_worker.schemas.chat_evaluation import ChatEvaluationManifest
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatRoute,
    MedicationChatSourceKind,
)

EVALUATION_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "knowledge" / "evaluation" / "chat_representative_queries.yaml"
)
SAFETY_RETRIEVAL_EVALUATION_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "knowledge" / "evaluation" / "chat_safety_retrieval_queries_v1.yaml"
)


def test_chat_representative_queries_define_balanced_source_contracts() -> None:
    manifest = yaml.safe_load(EVALUATION_PATH.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    validated = ChatEvaluationManifest.model_validate(manifest)

    assert manifest["schema_version"] == "chat-evaluation-v1"
    assert manifest["dataset_version"] == "chat-representative-v3"
    assert manifest["frontend_preset"] is False
    assert len(cases) == 13
    assert len(validated.cases) == 13
    assert Counter(case["category"] for case in cases) == {
        "RDB_ONLY": 3,
        "VECTOR_ONLY": 6,
        "RDB_AND_VECTOR": 3,
        "NO_SOURCE": 1,
    }

    query_ids = [case["query_id"] for case in cases]
    questions = [case["question"] for case in cases]
    assert len(query_ids) == len(set(query_ids))
    assert len(questions) == len(set(questions))
    losartan_case = next(case for case in cases if case["query_id"] == "vector-losartan-ingredient-family")
    assert losartan_case["expected"]["route"] == "MEDICATION_GUIDE"
    assert losartan_case["expected"]["required_source_kinds"] == [
        "PUBLIC_KNOWLEDGE",
    ]
    vitamin_b_function_case = next(case for case in cases if case["query_id"] == "vector-vitamin-b-family-function")
    assert vitamin_b_function_case["expected"]["route"] == "SUPPLEMENT_GUIDE"
    assert vitamin_b_function_case["expected"]["normalized_entities"] == [
        {
            "entity_type": "INGREDIENT_FAMILY",
            "canonical_name": "비타민 B",
        }
    ]
    vitamin_b_intake_case = next(case for case in cases if case["query_id"] == "clarification-vitamin-b-family-intake")
    assert vitamin_b_intake_case["expected"]["route"] == "CLARIFICATION"
    assert vitamin_b_intake_case["expected"]["required_source_kinds"] == []
    vitamin_b6_case = next(case for case in cases if case["query_id"] == "vector-vitamin-b6-intake")
    assert vitamin_b6_case["expected"]["normalized_entities"] == [
        {
            "entity_type": "INGREDIENT_NAME",
            "canonical_name": "비타민 B6",
        }
    ]
    interaction_tags = {tag for case in cases for tag in case["expected"]["intent_tags"]}
    assert {
        "DRUG_DRUG_INTERACTION",
        "DRUG_SUPPLEMENT_INTERACTION",
        "SUPPLEMENT_SUPPLEMENT_INTERACTION",
    } <= interaction_tags

    valid_routes = {route.value for route in MedicationChatRoute}
    valid_sources = {kind.value for kind in MedicationChatSourceKind}

    for case in cases:
        expected = case["expected"]
        required_sources = set(expected["required_source_kinds"])

        assert case["preconditions"]
        assert expected["route"] in valid_routes
        assert expected["intent_tags"]
        assert expected["normalized_entities"]
        assert expected["section_types"]
        assert required_sources <= valid_sources
        assert expected["safety_status"] in {"SAFE", "RESTRICTED", "BLOCKED"}
        assert expected["require_langsmith_trace"] is True
        assert expected["answer_requirements"]
        assert expected["forbidden_claims"]

        if case["category"] == "NO_SOURCE":
            assert not required_sources
        elif case["category"] == "RDB_ONLY":
            assert required_sources
            assert "PUBLIC_KNOWLEDGE" not in required_sources
        elif case["category"] == "VECTOR_ONLY":
            assert required_sources == {"PUBLIC_KNOWLEDGE"}
        else:
            assert "PUBLIC_KNOWLEDGE" in required_sources
            assert required_sources - {"PUBLIC_KNOWLEDGE"}


def test_chat_safety_retrieval_queries_define_twenty_fixed_cases() -> None:
    manifest = yaml.safe_load(SAFETY_RETRIEVAL_EVALUATION_PATH.read_text(encoding="utf-8"))
    validated = ChatEvaluationManifest.model_validate(manifest)

    assert validated.dataset_version == "chat-safety-retrieval-v1"
    assert len(validated.cases) == 20
    assert Counter(case.category.value for case in validated.cases) == {
        "RDB_ONLY": 7,
        "VECTOR_ONLY": 5,
        "RDB_AND_VECTOR": 2,
        "NO_SOURCE": 6,
    }
    assert all(case.expected.answer_requirements for case in validated.cases)
    assert all(case.expected.forbidden_claims for case in validated.cases)
    assert all(case.expected.required_answer_markers for case in validated.cases)
    assert all(case.expected.forbidden_answer_markers for case in validated.cases)

    greeting = next(case for case in validated.cases if case.query_id == "greeting-in-scope-boundary")
    assert greeting.expected.normalized_entities == []
    assert greeting.expected.section_types == []
    assert greeting.expected.route == MedicationChatRoute.OUT_OF_SCOPE

    dose_escalation = next(case for case in validated.cases if case.query_id == "medication-dose-escalation")
    assert dose_escalation.category.value == "NO_SOURCE"
    assert dose_escalation.expected.route == MedicationChatRoute.CLARIFICATION
    assert dose_escalation.expected.safety_status == SafetyStatus.RESTRICTED

    fatigue = next(case for case in validated.cases if case.query_id == "fatigue-triage-before-recommendation")
    assert fatigue.category.value == "NO_SOURCE"
    assert fatigue.expected.route == MedicationChatRoute.GENERAL_GUIDANCE
    assert fatigue.expected.safety_status == SafetyStatus.SAFE

    active_intake = next(case for case in validated.cases if case.query_id == "active-intake-prioritized-summary")
    assert active_intake.category.value == "RDB_ONLY"
    assert active_intake.expected.route == MedicationChatRoute.INTERACTION
    assert set(active_intake.expected.required_source_kinds) == {
        MedicationChatSourceKind.PATIENT_MEDICATION,
        MedicationChatSourceKind.PATIENT_SUPPLEMENT,
    }

    strict_pair_cases = {
        case.query_id: case
        for case in validated.cases
        if case.query_id in {
            "typo-magnesium-zinc-interaction",
            "typo-vitamin-d-calcium-interaction",
        }
    }
    assert {case.category.value for case in strict_pair_cases.values()} == {"NO_SOURCE"}
    assert {case.expected.route for case in strict_pair_cases.values()} == {MedicationChatRoute.RESTRICTED}
    assert {case.expected.safety_status for case in strict_pair_cases.values()} == {SafetyStatus.RESTRICTED}

    drug_food = next(case for case in validated.cases if case.query_id == "drug-food-tylenol-alcohol")
    assert drug_food.category.value == "RDB_ONLY"
    assert drug_food.expected.required_source_kinds == [MedicationChatSourceKind.MEDICATION_GUIDE]
