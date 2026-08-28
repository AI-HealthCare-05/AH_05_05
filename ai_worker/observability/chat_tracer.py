import asyncio
import hashlib
import hmac
import logging
import uuid
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, Protocol

from langsmith import Client, trace, tracing_context
from langsmith.run_trees import RunTree

from ai_worker.core.config import Config

logger = logging.getLogger(__name__)


class ChatSpan(Protocol):
    trace_id: str | None

    def end(
        self,
        outputs: Mapping[str, Any] | None = None,
    ) -> None: ...


class ChatTracer(Protocol):
    capture_content: bool

    def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        root: bool = False,
    ): ...

    def anonymize_identifier(
        self,
        value: str | int,
    ) -> str | None: ...

    async def aclose(self) -> None: ...


class _IdentifierAnonymizer:
    def __init__(self, salt: str | None) -> None:
        self._salt = salt.encode("utf-8") if salt else None

    def anonymize(
        self,
        value: str | int,
    ) -> str | None:
        if self._salt is None:
            return None
        digest = hmac.new(
            self._salt,
            str(value).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest[:16]


class _NoOpChatSpan:
    trace_id: str | None = None

    def end(
        self,
        outputs: Mapping[str, Any] | None = None,
    ) -> None:
        return None


class NoOpChatTracer:
    capture_content = False

    def __init__(self, *, hash_salt: str | None = None) -> None:
        self._anonymizer = _IdentifierAnonymizer(hash_salt)

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        root: bool = False,
    ):
        yield _NoOpChatSpan()

    def anonymize_identifier(
        self,
        value: str | int,
    ) -> str | None:
        return self._anonymizer.anonymize(value)

    async def aclose(self) -> None:
        return None


class _LangSmithChatSpan:
    def __init__(self, run: RunTree) -> None:
        self._run = run
        self._outputs: dict[str, Any] = {}
        trace_id = run.trace_id or run.id
        self.trace_id = str(trace_id)

    def end(
        self,
        outputs: Mapping[str, Any] | None = None,
    ) -> None:
        if outputs:
            self._outputs.update(outputs)

    def finish(self) -> None:
        self._run.end(outputs=self._outputs or None)


class LangSmithChatTracer:
    def __init__(
        self,
        *,
        client: Client,
        project_name: str,
        environment: str,
        capture_content: bool,
        hash_salt: str | None,
        close_timeout_seconds: float,
    ) -> None:
        self._client = client
        self._project_name = project_name
        self._environment = environment
        self.capture_content = capture_content
        self._anonymizer = _IdentifierAnonymizer(hash_salt)
        self._close_timeout_seconds = close_timeout_seconds

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        root: bool = False,
    ):
        run_id = uuid.uuid4() if root else None
        span_metadata = {
            "environment": self._environment,
            **dict(metadata or {}),
        }
        with tracing_context(
            enabled=True,
            client=self._client,
            project_name=self._project_name,
        ):
            async with trace(
                name,
                run_type=run_type,
                inputs=dict(inputs or {}),
                metadata=span_metadata,
                client=self._client,
                project_name=self._project_name,
                run_id=run_id,
            ) as run:
                span = _LangSmithChatSpan(run)
                try:
                    yield span
                finally:
                    span.finish()

    def anonymize_identifier(
        self,
        value: str | int,
    ) -> str | None:
        return self._anonymizer.anonymize(value)

    async def aclose(self) -> None:
        await asyncio.to_thread(
            self._client.close,
            timeout=self._close_timeout_seconds,
        )


class SafeChatTracer:
    def __init__(self, delegate: ChatTracer) -> None:
        self._delegate = delegate
        self.capture_content = delegate.capture_content

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        root: bool = False,
    ):
        manager = self._delegate.span(
            name,
            run_type=run_type,
            inputs=inputs,
            metadata=metadata,
            root=root,
        )
        try:
            span = await manager.__aenter__()
        except Exception:
            logger.warning(
                "LangSmith span 시작에 실패했습니다: name=%s",
                name,
                exc_info=True,
            )
            yield _NoOpChatSpan()
            return

        business_error: BaseException | None = None
        business_traceback: TracebackType | None = None
        try:
            yield span
        except BaseException as error:
            business_error = error
            business_traceback = error.__traceback__

        try:
            await manager.__aexit__(
                type(business_error) if business_error else None,
                business_error,
                business_traceback,
            )
        except Exception:
            logger.warning(
                "LangSmith span 종료에 실패했습니다: name=%s",
                name,
                exc_info=True,
            )

        if business_error is not None:
            raise business_error.with_traceback(business_traceback)

    def anonymize_identifier(
        self,
        value: str | int,
    ) -> str | None:
        return self._delegate.anonymize_identifier(value)

    async def aclose(self) -> None:
        try:
            await self._delegate.aclose()
        except Exception:
            logger.warning(
                "LangSmith trace buffer 종료에 실패했습니다.",
                exc_info=True,
            )


def _secret_value(secret) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


def build_chat_tracer(
    settings: Config,
    *,
    client_factory: Callable[..., Client] = Client,
) -> ChatTracer:
    hash_salt = _secret_value(settings.LANGSMITH_HASH_SALT)
    if not settings.LANGSMITH_TRACING:
        return NoOpChatTracer(hash_salt=hash_salt)

    api_key = _secret_value(settings.LANGSMITH_API_KEY)
    if api_key is None:
        logger.warning(
            "LANGSMITH_TRACING이 켜졌지만 API Key가 없어 추적을 비활성화합니다."
        )
        return NoOpChatTracer(hash_salt=hash_salt)

    try:
        client = client_factory(
            api_url=settings.LANGSMITH_ENDPOINT,
            api_key=api_key,
            workspace_id=(settings.LANGSMITH_WORKSPACE_ID or None),
            hide_inputs=not settings.LANGSMITH_CAPTURE_CONTENT,
            hide_outputs=not settings.LANGSMITH_CAPTURE_CONTENT,
            auto_batch_tracing=True,
        )
    except Exception:
        logger.warning(
            "LangSmith Client 구성에 실패해 추적을 비활성화합니다.",
            exc_info=True,
        )
        return NoOpChatTracer(hash_salt=hash_salt)

    return SafeChatTracer(
        LangSmithChatTracer(
            client=client,
            project_name=settings.LANGSMITH_PROJECT,
            environment=settings.LANGSMITH_ENVIRONMENT,
            capture_content=settings.LANGSMITH_CAPTURE_CONTENT,
            hash_salt=hash_salt,
            close_timeout_seconds=(settings.LANGSMITH_CLOSE_TIMEOUT_SECONDS),
        )
    )
