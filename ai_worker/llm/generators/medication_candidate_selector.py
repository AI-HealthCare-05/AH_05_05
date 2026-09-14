import asyncio
import json
from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.llm.prompts.medication_candidate_prompt import MEDICATION_CANDIDATE_PROMPT
from ai_worker.schemas.medication_chat import MedicationGuideFact


class AsyncMedicationCandidateClient(Protocol):
    async def ainvoke(self, messages: Any, /) -> dict[str, Any]: ...


class OpenAIMedicationCandidateSelector:
    _MAX_QUERY_LENGTH = 256
    _MAX_CANDIDATE_COUNT = 5
    _MAX_PRODUCT_NAME_LENGTH = 256

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncMedicationCandidateClient | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        if timeout_seconds <= 0:
            raise ValueError("LLM 선택 제한 시간은 양수여야 합니다.")
        self._model_name = normalized_model
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._chat_model = (
            None
            if client is not None
            else ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=0,
            )
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def select(
        self,
        *,
        query: str,
        candidates: list[MedicationGuideFact],
    ) -> int | None:
        if not self._is_within_identity_bounds(query=query, candidates=candidates):
            return None

        candidate_ids = [candidate.medication_guide_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            return None

        messages = MEDICATION_CANDIDATE_PROMPT.format_messages(
            payload_json=json.dumps(
                {
                    "query": query,
                    "candidates": [
                        {
                            "medication_guide_id": candidate.medication_guide_id,
                            "product_name": candidate.product_name,
                        }
                        for candidate in candidates
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        try:
            if self._client is not None:
                client = self._client
            else:
                assert self._chat_model is not None
                client = self._chat_model.with_structured_output(
                    self._selection_schema(candidate_ids), method="json_schema", strict=True
                )
            raw_response = await asyncio.wait_for(
                client.ainvoke(messages),
                timeout=self._timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return None
        return self._selected_candidate_id(raw_response=raw_response, allowed_ids=set(candidate_ids))

    @classmethod
    def _is_within_identity_bounds(
        cls,
        *,
        query: str,
        candidates: list[MedicationGuideFact],
    ) -> bool:
        return (
            isinstance(query, str)
            and bool(query.strip())
            and len(query) <= cls._MAX_QUERY_LENGTH
            and 0 < len(candidates) <= cls._MAX_CANDIDATE_COUNT
            and all(len(candidate.product_name) <= cls._MAX_PRODUCT_NAME_LENGTH for candidate in candidates)
        )

    @staticmethod
    def _selection_schema(candidate_ids: list[int]) -> dict[str, Any]:
        # A dict schema keeps the raw JSON value intact. A Pydantic Literal[1]
        # can coerce true to 1 before our strict identifier check sees it.
        return {
            "title": "MedicationCandidateSelection",
            "type": "object",
            "properties": {
                "selected_candidate_id": {"type": ["integer", "null"], "enum": [*candidate_ids, None]},
            },
            "required": ["selected_candidate_id"],
            "additionalProperties": False,
        }

    @staticmethod
    def _selected_candidate_id(
        *,
        raw_response: dict[str, Any],
        allowed_ids: set[int],
    ) -> int | None:
        response = raw_response
        if type(response) is not dict or set(response) != {"selected_candidate_id"}:
            return None
        selected_candidate_id = response["selected_candidate_id"]
        if selected_candidate_id is None:
            return None
        if type(selected_candidate_id) is not int or selected_candidate_id not in allowed_ids:
            return None
        return selected_candidate_id
