from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda

from ai_worker.llm.generators.intake_report_cards_generator import _spacing_messages
from ai_worker.llm.prompts import prompt_assets
from ai_worker.reports import report_rag_pipeline


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    prompt_assets.load_prompt_asset.cache_clear()
    yield
    prompt_assets.load_prompt_asset.cache_clear()


@pytest.mark.parametrize("stage", ["planner", "claims", "verifier", "spacing", "spacing_retry"])
def test_report_prompt_document_is_loadable(stage):
    assert prompt_assets.load_prompt_asset(f"intake_report_{stage}.md").strip()


@pytest.mark.asyncio
async def test_rag_chains_use_external_prompt_documents(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    for stage in ("planner", "claims", "verifier"):
        (tmp_path / "assets" / f"intake_report_{stage}.md").write_text(f"external:{stage}", encoding="utf-8")
    monkeypatch.setattr(prompt_assets, "files", lambda package: tmp_path)

    class Model:
        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, *args, **kwargs):
            return RunnableLambda(lambda messages: messages)

    monkeypatch.setattr(report_rag_pipeline, "ChatOpenAI", Model)
    monkeypatch.setattr(report_rag_pipeline, "load_report_rag_source_registry", lambda: {})
    pipeline = report_rag_pipeline.build_openai_report_rag_pipeline(
        retriever=None, dataset_version="test", model="test", api_key=None
    )
    for stage, chain in (
        ("planner", pipeline._planner),
        ("claims", pipeline._claim_writer),
        ("verifier", pipeline._verifier),
    ):
        messages = await chain.ainvoke({"example": "data"})
        assert messages[0].content == f"external:{stage}"
        assert messages[1].content == '{"example":"data"}'


def test_spacing_and_retry_use_documents_without_interpreting_error_braces():
    messages = _spacing_messages(SimpleNamespace(payload=lambda batch: []), "bad {field}")
    assert messages[0].content == prompt_assets.load_prompt_asset("intake_report_spacing.md")
    assert messages[-1].content == prompt_assets.load_prompt_asset("intake_report_spacing_retry.md").format(
        repair_error="bad {field}"
    )


@pytest.mark.parametrize("content", [None, "  \n"])
def test_missing_or_empty_report_prompt_fails_closed(tmp_path, monkeypatch, content):
    (tmp_path / "assets").mkdir()
    if content is not None:
        (tmp_path / "assets" / "intake_report_planner.md").write_text(content, encoding="utf-8")
    prompt_assets.load_prompt_asset.cache_clear()
    monkeypatch.setattr(prompt_assets, "files", lambda package: tmp_path)
    try:
        with pytest.raises(FileNotFoundError if content is None else ValueError):
            prompt_assets.load_prompt_asset("intake_report_planner.md")
    finally:
        prompt_assets.load_prompt_asset.cache_clear()
