from pathlib import Path

import yaml


DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "knowledge"
    / "evaluation"
    / "chat_conversation_gate_queries_v1.yaml"
)


def test_conversation_gate_dataset_covers_required_boundaries() -> None:
    manifest = yaml.safe_load(DATASET.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    ids = {case["query_id"] for case in cases}

    assert manifest["schema_version"] == "conversation-gate-evaluation-v1"
    assert manifest["dataset_version"] == "chat-conversation-gate-v1"
    assert len(cases) == 18
    assert {
        "greeting-friendly",
        "casual-friendly",
        "vague-symptom-follow-up",
        "specific-abdominal-symptom",
        "urgent-substance-health-event",
        "harmful-weapon-instructions",
        "harmful-illegal-drug-production",
        "politics-out-of-scope",
        "medication-regression",
        "interaction-regression",
    } <= ids

    for case in cases:
        expected = case["expected"]
        assert case["question"]
        assert expected["intent"]
        assert expected["safety_signal"]
        assert expected["disposition"]
        assert expected["expected_route"]
        assert isinstance(expected["show_active_medications"], bool)
        assert expected["required_markers"]
        assert "forbidden_markers" in expected
