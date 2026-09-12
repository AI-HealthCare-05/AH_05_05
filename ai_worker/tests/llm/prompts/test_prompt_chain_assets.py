from importlib import import_module

import pytest


def _prompt_assets_module():
    return import_module("ai_worker.llm.prompts.prompt_assets")


def test_v7_prompt_pack_loads_only_requested_stage() -> None:
    prompt_assets = _prompt_assets_module()

    document = prompt_assets.load_prompt_chain_stage(
        "medication_chat_prompt_v7.md",
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
