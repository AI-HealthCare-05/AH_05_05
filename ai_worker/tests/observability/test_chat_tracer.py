from contextlib import asynccontextmanager

from ai_worker.core.config import Config
from ai_worker.observability.chat_tracer import (
    NoOpChatTracer,
    SafeChatTracer,
    build_chat_tracer,
)


class CapturingClientFactory:
    def __init__(self) -> None:
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return object()


class FailingDelegateTracer:
    capture_content = False

    def __init__(
        self,
        *,
        fail_on_start: bool = False,
        fail_on_end: bool = False,
        fail_on_close: bool = False,
    ) -> None:
        self.fail_on_start = fail_on_start
        self.fail_on_end = fail_on_end
        self.fail_on_close = fail_on_close

    @asynccontextmanager
    async def span(self, name, **kwargs):
        if self.fail_on_start:
            raise RuntimeError("start failed")
        yield object()
        if self.fail_on_end:
            raise RuntimeError("end failed")

    def anonymize_identifier(self, value):
        return None

    async def aclose(self) -> None:
        if self.fail_on_close:
            raise RuntimeError("close failed")


async def test_noop_tracer_returns_no_trace_id() -> None:
    tracer = NoOpChatTracer()

    async with tracer.span(
        "chat.answer",
        root=True,
    ) as span:
        span.end({"status": "SAFE"})

    assert span.trace_id is None
    assert tracer.anonymize_identifier(1) is None


def test_anonymize_identifier_is_stable_and_does_not_expose_id() -> None:
    tracer = NoOpChatTracer(hash_salt="test-salt")

    first = tracer.anonymize_identifier(1)
    second = tracer.anonymize_identifier(1)

    assert first == second
    assert first != "1"
    assert first is not None
    assert len(first) == 16


def test_builder_falls_back_to_noop_without_api_key() -> None:
    settings = Config(
        LANGSMITH_TRACING=True,
        LANGSMITH_API_KEY=None,
        _env_file=None,
    )

    tracer = build_chat_tracer(settings)

    assert isinstance(tracer, NoOpChatTracer)


def test_builder_hides_inputs_and_outputs_by_default() -> None:
    factory = CapturingClientFactory()
    settings = Config(
        LANGSMITH_TRACING=True,
        LANGSMITH_API_KEY="test-key",
        LANGSMITH_CAPTURE_CONTENT=False,
        _env_file=None,
    )

    tracer = build_chat_tracer(
        settings,
        client_factory=factory,
    )

    assert not isinstance(tracer, NoOpChatTracer)
    assert factory.kwargs is not None
    assert factory.kwargs["hide_inputs"] is True
    assert factory.kwargs["hide_outputs"] is True


async def test_safe_tracer_ignores_span_start_failure() -> None:
    tracer = SafeChatTracer(
        FailingDelegateTracer(fail_on_start=True),
    )

    async with tracer.span("chat.answer") as span:
        assert span.trace_id is None


async def test_safe_tracer_ignores_span_end_failure() -> None:
    tracer = SafeChatTracer(
        FailingDelegateTracer(fail_on_end=True),
    )

    async with tracer.span("chat.answer"):
        completed = True

    assert completed is True


async def test_safe_tracer_ignores_close_failure() -> None:
    tracer = SafeChatTracer(
        FailingDelegateTracer(fail_on_close=True),
    )

    await tracer.aclose()


async def test_safe_tracer_preserves_business_failure() -> None:
    tracer = SafeChatTracer(FailingDelegateTracer())

    try:
        async with tracer.span("chat.answer"):
            raise ValueError("business failed")
    except ValueError as error:
        assert str(error) == "business failed"
    else:
        raise AssertionError("비즈니스 예외가 그대로 전달되어야 합니다.")
