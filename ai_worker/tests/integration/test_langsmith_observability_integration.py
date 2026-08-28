import asyncio

import pytest
from langsmith import Client

from ai_worker.core.config import Config
from ai_worker.observability.chat_tracer import build_chat_tracer

settings = Config()
live_test_enabled = (
    settings.RUN_LANGSMITH_INTEGRATION_TESTS and settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY is not None
)

pytestmark = pytest.mark.skipif(
    not live_test_enabled,
    reason=(
        "실제 LangSmith 테스트는 RUN_LANGSMITH_INTEGRATION_TESTS=1, "
        "LANGSMITH_TRACING=true, LANGSMITH_API_KEY가 필요합니다."
    ),
)


async def test_langsmith_accepts_synthetic_chat_trace() -> None:
    tracer = build_chat_tracer(settings)

    async with tracer.span(
        "chat.observability.integration",
        root=True,
        inputs={"question": "가상 데이터 기반 테스트 질문"},
        metadata={"synthetic": True},
    ) as span:
        span.end({"status": "SAFE"})

    trace_id = span.trace_id
    await tracer.aclose()

    assert trace_id is not None
    assert settings.LANGSMITH_API_KEY is not None

    client = Client(
        api_url=settings.LANGSMITH_ENDPOINT,
        api_key=settings.LANGSMITH_API_KEY.get_secret_value(),
        workspace_id=settings.LANGSMITH_WORKSPACE_ID or None,
    )
    try:
        projects = await asyncio.to_thread(
            lambda: list(
                client.list_projects(
                    name=settings.LANGSMITH_PROJECT,
                    limit=2,
                )
            )
        )
        assert len(projects) == 1

        saved_run = None
        for _ in range(10):
            matching_runs = [
                run
                async for run in client.runs.query(
                    project_ids=[str(projects[0].id)],
                    trace_id=trace_id,
                    page_size=1,
                    selects=["ID", "TRACE_ID", "NAME"],
                )
            ]
            if matching_runs:
                saved_run = matching_runs[0]
                break
            await asyncio.sleep(0.5)
    finally:
        client.close(timeout=settings.LANGSMITH_CLOSE_TIMEOUT_SECONDS)

    assert saved_run is not None
    assert str(saved_run.trace_id) == trace_id
    assert saved_run.name == "chat.observability.integration"
