import json
import re
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.domain.errors import MedicationNoteSummaryGenerationError
from ai_worker.llm.prompts.prompt_assets import load_prompt_template_document
from ai_worker.schemas.medication_note_summary import (
    MedicationNoteSummaryPayload,
    MedicationNoteSummarySelection,
)

MEDICATION_NOTE_SUMMARY_PROMPT_VERSION = "medication-note-summary-prompt-v1"


class AsyncMedicationNoteSummaryClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> MedicationNoteSummaryPayload | dict[str, Any]: ...


PROMPT_DOCUMENT = load_prompt_template_document("medication_note_summary_prompt_v1.md")
PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", PROMPT_DOCUMENT.system),
        ("human", PROMPT_DOCUMENT.user),
    ]
)


class MedicationNoteSummaryGenerator:
    _CAUSAL_CLAIM_PATTERN = re.compile(
        r"(?:약물|약|복용).{0,16}(?:때문|원인|부작용)|"
        r"(?:부작용|원인).{0,16}(?:약물|약|복용)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        client: AsyncMedicationNoteSummaryClient,
    ) -> None:
        self._client = client

    async def generate(
        self,
        *,
        selection: MedicationNoteSummarySelection,
    ) -> MedicationNoteSummaryPayload:
        messages = PROMPT.format_messages(
            selection_json=json.dumps(
                selection.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        raw_payload = await self._client.ainvoke(messages)
        payload = (
            raw_payload
            if isinstance(raw_payload, MedicationNoteSummaryPayload)
            else MedicationNoteSummaryPayload.model_validate(raw_payload)
        )
        self._validate_payload(selection=selection, payload=payload)
        return payload

    @classmethod
    def _validate_payload(
        cls,
        *,
        selection: MedicationNoteSummarySelection,
        payload: MedicationNoteSummaryPayload,
    ) -> None:
        expected_note_ids = {
            episode.care_episode_id: {
                note.medication_note_id for note in episode.notes
            }
            for episode in selection.episodes
        }
        actual_episode_ids = [episode.care_episode_id for episode in payload.episodes]
        if len(actual_episode_ids) != len(set(actual_episode_ids)) or set(actual_episode_ids) != set(expected_note_ids):
            raise MedicationNoteSummaryGenerationError("진료 건 식별자가 입력과 일치하지 않습니다.")

        for episode in payload.episodes:
            note_ids = [note.medication_note_id for note in episode.note_summaries]
            if len(note_ids) != len(set(note_ids)) or set(note_ids) != expected_note_ids[episode.care_episode_id]:
                raise MedicationNoteSummaryGenerationError("메모 식별자가 입력과 일치하지 않습니다.")
            phrases = [
                *(note.summary for note in episode.note_summaries),
                episode.one_line_summary,
            ]
            if any(cls._CAUSAL_CLAIM_PATTERN.search(phrase) for phrase in phrases):
                raise MedicationNoteSummaryGenerationError("메모에 없는 인과 판단은 요약할 수 없습니다.")


def build_medication_note_summary_generator(
    *,
    model: str,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 15.0,
    max_retries: int = 1,
) -> MedicationNoteSummaryGenerator:
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
    client = ChatOpenAI(
        model=normalized_model,
        temperature=0,
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=max_retries,
    ).with_structured_output(
        MedicationNoteSummaryPayload,
        method="json_schema",
        strict=True,
    )
    return MedicationNoteSummaryGenerator(client=client)
