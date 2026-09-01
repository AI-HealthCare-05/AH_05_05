"""Privacy-bounded OpenAI Responses provider for evidence-ID selection only."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

import httpx2
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.services.medication_ocr_v3.domain.grounding import EvidenceCatalog, GroundingSelection

PROMPT_VERSION = "medication_grounding_v3"
SCHEMA_VERSION = "medication_block_selection_v3"

_OFFICIAL_BASE_URL = "https://api.openai.com/v1"
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.md"
_TIMEOUT = httpx2.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)
_RISKY_AMBIENT_VARIABLES = frozenset(
    {
        "OPENAI_BASE_URL",
        "OPENAI_CUSTOM_HEADERS",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "OPENAI_WEBHOOK_SECRET",
    }
)

# These libraries log request metadata at INFO. Keep the provider boundary quiet so
# neither the official endpoint nor evidence payloads can enter application logs.
for _logger_name in ("openai", "httpx", "httpx2"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


class LlmErrorCode(StrEnum):
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_CONNECTION_FAILED = "LLM_CONNECTION_FAILED"
    LLM_AUTH_REJECTED = "LLM_AUTH_REJECTED"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_UPSTREAM_FAILED = "LLM_UPSTREAM_FAILED"
    LLM_REFUSAL = "LLM_REFUSAL"
    LLM_INCOMPLETE = "LLM_INCOMPLETE"
    LLM_SCHEMA_INVALID = "LLM_SCHEMA_INVALID"
    LLM_CONFIGURATION_REJECTED = "LLM_CONFIGURATION_REJECTED"
    LLM_INPUT_INVALID = "LLM_INPUT_INVALID"


class LlmProviderError(RuntimeError):
    """A stable provider failure containing no upstream or evidence details."""

    def __init__(self, code: LlmErrorCode, status_code: int) -> None:
        super().__init__(code.value)
        self.code = code
        self.status_code = status_code


class _ResponsesResource(Protocol):
    async def create(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    @property
    def responses(self) -> _ResponsesResource: ...

    async def close(self) -> None: ...


class GroundedStructurer(Protocol):
    async def select(self, catalog: EvidenceCatalog) -> GroundingSelection: ...

    async def aclose(self) -> None: ...


class OpenAIGroundedStructurer:
    """Call OpenAI once with a bounded catalog and accept only schema-valid IDs."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-5.6-terra",
        client: _OpenAIClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client
        self._closed = False

    def __repr__(self) -> str:
        return "OpenAIGroundedStructurer()"

    @property
    def model_version(self) -> str:
        return self._model

    async def __aenter__(self) -> OpenAIGroundedStructurer:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.close()
            except Exception:
                raise LlmProviderError(LlmErrorCode.LLM_UPSTREAM_FAILED, 502) from None

    async def select(self, catalog: EvidenceCatalog) -> GroundingSelection:
        if self._closed:
            raise LlmProviderError(LlmErrorCode.LLM_CONFIGURATION_REJECTED, 503)
        try:
            prompt = _PROMPT_PATH.read_text(encoding="utf-8")
            model_input = json.dumps(
                catalog.to_llm_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (KeyError, OSError, TypeError, UnicodeError, ValueError):
            raise LlmProviderError(LlmErrorCode.LLM_INPUT_INVALID, 500) from None

        client = await self._get_client()
        try:
            response = await client.responses.create(
                model=self._model,
                instructions=prompt,
                input=model_input,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": SCHEMA_VERSION,
                        "schema": GroundingSelection.model_json_schema(by_alias=True),
                        "strict": True,
                    }
                },
                store=False,
                max_output_tokens=4_096,
                truncation="disabled",
            )
        except APITimeoutError:
            raise LlmProviderError(LlmErrorCode.LLM_TIMEOUT, 504) from None
        except APIConnectionError:
            raise LlmProviderError(LlmErrorCode.LLM_CONNECTION_FAILED, 502) from None
        except APIStatusError as error:
            raise _status_error(error.status_code) from None
        except Exception:
            raise LlmProviderError(LlmErrorCode.LLM_UPSTREAM_FAILED, 502) from None

        try:
            if _attribute(response, "status") != "completed":
                raise LlmProviderError(LlmErrorCode.LLM_INCOMPLETE, 502)
            if _contains_refusal(response):
                raise LlmProviderError(LlmErrorCode.LLM_REFUSAL, 502)
            output_text = _attribute(response, "output_text")
            if not isinstance(output_text, str) or not output_text:
                raise LlmProviderError(LlmErrorCode.LLM_INCOMPLETE, 502)
            return GroundingSelection.model_validate_json(output_text)
        except LlmProviderError:
            raise
        except (ValidationError, TypeError, ValueError):
            raise LlmProviderError(LlmErrorCode.LLM_SCHEMA_INVALID, 502) from None
        except Exception:
            raise LlmProviderError(LlmErrorCode.LLM_SCHEMA_INVALID, 502) from None

    async def _get_client(self) -> _OpenAIClient:
        if self._client is not None:
            return self._client
        if any(variable in os.environ for variable in _RISKY_AMBIENT_VARIABLES):
            raise LlmProviderError(LlmErrorCode.LLM_CONFIGURATION_REJECTED, 503)

        try:
            http_client = httpx2.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
            )
        except Exception:
            raise LlmProviderError(LlmErrorCode.LLM_CONFIGURATION_REJECTED, 503) from None
        try:
            sdk_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=_OFFICIAL_BASE_URL,
                max_retries=0,
                http_client=http_client,
            )
        except Exception:
            try:
                await http_client.aclose()
            except Exception:
                pass
            raise LlmProviderError(LlmErrorCode.LLM_CONFIGURATION_REJECTED, 503) from None
        self._client = cast(_OpenAIClient, sdk_client)
        return self._client


def _status_error(status_code: int) -> LlmProviderError:
    if status_code == 400:
        return LlmProviderError(LlmErrorCode.LLM_CONFIGURATION_REJECTED, 503)
    if status_code in {401, 403}:
        return LlmProviderError(LlmErrorCode.LLM_AUTH_REJECTED, 502)
    if status_code == 429:
        return LlmProviderError(LlmErrorCode.LLM_RATE_LIMITED, 503)
    return LlmProviderError(LlmErrorCode.LLM_UPSTREAM_FAILED, 502)


def _attribute(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return cast(object | None, getattr(value, name, None))


def _contains_refusal(response: object) -> bool:
    output = _attribute(response, "output")
    if not isinstance(output, list):
        return False
    for item in output:
        if _attribute(item, "type") == "refusal":
            return True
        content = _attribute(item, "content")
        if not isinstance(content, list):
            continue
        if any(_attribute(part, "type") == "refusal" for part in content):
            return True
    return False
