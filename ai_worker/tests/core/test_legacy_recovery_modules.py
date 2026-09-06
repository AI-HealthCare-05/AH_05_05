from importlib.util import find_spec


def test_legacy_discharge_recovery_prompt_modules_are_removed() -> None:
    legacy_modules = (
        "ai_worker.llm.prompts.chat_answer_prompt",
        "ai_worker.llm.prompts.chat_classification_prompt",
        "ai_worker.llm.prompts.recovery_guide_prompt",
    )

    remaining_modules = [
        module_name
        for module_name in legacy_modules
        if find_spec(module_name) is not None
    ]

    assert remaining_modules == []
