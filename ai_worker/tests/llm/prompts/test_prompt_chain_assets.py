from importlib import import_module

import pytest


def _prompt_assets_module():
    return import_module("ai_worker.llm.prompts.prompt_assets")


def test_v7_prompt_pack_loads_only_requested_stage() -> None:
    prompt_assets = _prompt_assets_module()

    document = prompt_assets.load_prompt_chain_stage(
        prompt_assets.MedicationPromptStage.DIRECTIONAL_QUERY,
    )

    assert "후보 밖의 제품명" in document.common
    assert "검색 방향" in document.system
    assert "{question}" in document.user
    assert "FUNCTION과 CAUTION" in document.examples
    assert "복약메모" not in document.user
    for element in ("역할(Role)", "작업(Task)", "내용(Content)", "형식(Format)", "제약(Constraint)"):
        assert element in document.system
    assert document.compiled_system.startswith(document.common)
    assert document.system in document.compiled_system
    assert document.examples in document.compiled_system
    assert "예시(Example)" in document.compiled_system


def test_v9_prompt_pack_is_the_runtime_default_and_keeps_all_chain_stages() -> None:
    prompt_assets = _prompt_assets_module()

    assert prompt_assets.MEDICATION_CHAT_PROMPT_CHAIN_ASSET == "medication_chat_prompt_v9.md"
    for stage in prompt_assets.MedicationPromptStage:
        document = prompt_assets.load_prompt_chain_stage(stage)
        assert document.system
        assert document.user
        assert document.examples


def test_v8_conversation_gate_limits_note_summary_to_explicit_requests() -> None:
    prompt_assets = _prompt_assets_module()

    document = prompt_assets.load_prompt_chain_stage(
        prompt_assets.MedicationPromptStage.CONVERSATION_GATE,
    )

    assert "복약메모·복약기록을 정리·요약" in document.system
    assert "잠 잘자려면 뭘 먹어야해?" in document.system


def test_v8_conversation_gate_routes_registered_lists_and_symptom_medicine_questions() -> None:
    prompt_assets = _prompt_assets_module()

    document = prompt_assets.load_prompt_chain_stage(
        prompt_assets.MedicationPromptStage.CONVERSATION_GATE,
    )

    assert "ACTIVE_MEDICATION_LIST" in document.system
    assert "ACTIVE_SUPPLEMENT_LIST" in document.system
    assert "MEDICATION_GUIDE_FOLLOW_UP" in document.system
    assert "SYMPTOM_MEDICATION_GUIDANCE" in document.system
    assert "symptom_context" in document.compiled_system


def test_v8_answer_generation_preserves_functional_goal_ingredient_lists() -> None:
    prompt_assets = _prompt_assets_module()

    document = prompt_assets.load_prompt_chain_stage(
        prompt_assets.MedicationPromptStage.ANSWER_GENERATION,
    )

    assert "🧬 **성분**" in document.system
    assert "기능 설명 문장" in document.system


@pytest.mark.parametrize(
    ("stage_name", "uses_directional_stimulus"),
    [
        ("CONVERSATION_GATE", False),
        ("DIRECTIONAL_QUERY", True),
        ("EVIDENCE_REASONING", True),
        ("ANSWER_GENERATION", False),
    ],
)
def test_primary_prompt_stages_expose_labeled_prompt_elements(
    stage_name: str,
    uses_directional_stimulus: bool,
) -> None:
    prompt_assets = _prompt_assets_module()
    stage = getattr(prompt_assets.MedicationPromptStage, stage_name)

    document = prompt_assets.load_prompt_chain_stage(stage)

    for element in (
        "[역할(Role)]",
        "[작업(Task)]",
        "[내용(Content)]",
        "[형식(Format)]",
        "[제약(Constraint)]",
        "[예시(Example)]",
    ):
        assert element in document.compiled_system
    assert ("[방향 자극(Directional Stimulus)]" in document.compiled_system) is uses_directional_stimulus


def test_stage_parser_rejects_missing_stage_marker() -> None:
    prompt_assets = _prompt_assets_module()

    with pytest.raises(ValueError, match="프롬프트 구역 표시"):
        prompt_assets.parse_prompt_chain_stage_document(
            """
<!-- prompt:common:system:start -->
공통 규칙
<!-- prompt:common:system:end -->
""",
            prompt_assets.MedicationPromptStage.ANSWER_GENERATION,
        )


def test_stage_parser_rejects_duplicate_stage_marker() -> None:
    prompt_assets = _prompt_assets_module()
    content = """
<!-- prompt:common:system:start -->
공통 규칙
<!-- prompt:common:system:end -->
<!-- prompt:answer_generation:system:start -->
첫 번째 시스템 규칙
<!-- prompt:answer_generation:system:end -->
<!-- prompt:answer_generation:system:start -->
두 번째 시스템 규칙
<!-- prompt:answer_generation:system:end -->
<!-- prompt:answer_generation:user:start -->
{payload_json}
<!-- prompt:answer_generation:user:end -->
<!-- prompt:answer_generation:examples:start -->
예시
<!-- prompt:answer_generation:examples:end -->
"""

    with pytest.raises(ValueError, match="프롬프트 구역 표시"):
        prompt_assets.parse_prompt_chain_stage_document(
            content,
            prompt_assets.MedicationPromptStage.ANSWER_GENERATION,
        )


def test_stage_parser_rejects_blank_section() -> None:
    prompt_assets = _prompt_assets_module()
    content = """
<!-- prompt:common:system:start -->
공통 규칙
<!-- prompt:common:system:end -->
<!-- prompt:conversation_gate:system:start -->

<!-- prompt:conversation_gate:system:end -->
<!-- prompt:conversation_gate:user:start -->
{question}
<!-- prompt:conversation_gate:user:end -->
<!-- prompt:conversation_gate:examples:start -->
예시
<!-- prompt:conversation_gate:examples:end -->
"""

    with pytest.raises(ValueError, match="비어 있을 수 없습니다"):
        prompt_assets.parse_prompt_chain_stage_document(
            content,
            prompt_assets.MedicationPromptStage.CONVERSATION_GATE,
        )
