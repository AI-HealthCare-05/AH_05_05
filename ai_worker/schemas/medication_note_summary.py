from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class MedicationNoteSummaryScope(StrEnum):
    RECENT_SIX_MONTHS = "RECENT_SIX_MONTHS"
    ALL_HISTORY = "ALL_HISTORY"


class MedicationNoteSummaryNote(BaseModel):
    medication_note_id: int = Field(gt=0)
    dosed_at: datetime
    body: str = Field(min_length=1, max_length=500)
    medication_name: str | None = None


class MedicationNoteSummaryEpisode(BaseModel):
    care_episode_id: int = Field(gt=0)
    care_episode_alias: str | None = None
    hospital_name: str | None = None
    medication_names: list[str] = Field(default_factory=list)
    notes: list[MedicationNoteSummaryNote] = Field(min_length=1)


class MedicationNoteSummarySelection(BaseModel):
    scope: MedicationNoteSummaryScope
    episodes: list[MedicationNoteSummaryEpisode] = Field(default_factory=list)
    has_more_episodes: bool = False


class MedicationNoteSummaryNotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    medication_note_id: int = Field(gt=0)
    summary: str = Field(min_length=1, max_length=180)


class MedicationNoteEpisodeSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    care_episode_id: int = Field(gt=0)
    note_summaries: list[MedicationNoteSummaryNotePayload] = Field(min_length=1)
    one_line_summary: str = Field(min_length=1, max_length=240)


class MedicationNoteSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    episodes: list[MedicationNoteEpisodeSummaryPayload] = Field(default_factory=list)


class MedicationNoteSummaryProvider(Protocol):
    async def list_episodes(
        self,
        *,
        user_id: int,
        scope: MedicationNoteSummaryScope,
    ) -> MedicationNoteSummarySelection: ...
