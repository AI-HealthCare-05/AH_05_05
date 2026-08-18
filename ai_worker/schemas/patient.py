import re
from datetime import date, datetime
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_validator,
)

from ai_worker.schemas.enums import InstructionType


class PatientMedication(BaseModel):
    """사용자가 확인하고 저장한 복약 정보."""

    medication_id: int | None = None
    name: str = Field(
        validation_alias=AliasChoices(
            "name",
            "drug_name",
        )
    )
    dose: str | None = None
    times_per_day: int | None = None
    note: str | None = None
    days: int | None = None
    prescribed_at: date | None = None

    # 기존 코드와 단계적으로 연동하기 위한 임시 호환 필드
    source_field_ids: list[int] = Field(
        default_factory=list,
        exclude=True,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(
        cls,
        data: Any,
    ) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)

        if (
            normalized.get("times_per_day") is None
            and normalized.get("frequency")
        ):
            matched = re.search(
                r"\d+",
                str(normalized["frequency"]),
            )
            if matched:
                normalized["times_per_day"] = int(
                    matched.group()
                )

        if (
            normalized.get("days") is None
            and normalized.get("duration")
        ):
            matched = re.search(
                r"\d+",
                str(normalized["duration"]),
            )
            if matched:
                normalized["days"] = int(
                    matched.group()
                )

        if (
            normalized.get("note") is None
            and normalized.get(
                "administration_instruction"
            )
        ):
            normalized["note"] = normalized[
                "administration_instruction"
            ]

        return normalized

    @property
    def drug_name(self) -> str:
        """기존 RAG·LLM 코드가 사용하는 이전 속성명."""

        return self.name

    @property
    def frequency(self) -> str | None:
        """기존 프롬프트에서 사용하는 복용 횟수 표현."""

        if self.times_per_day is None:
            return None

        return f"1일 {self.times_per_day}회"

    @property
    def duration(self) -> str | None:
        """기존 프롬프트에서 사용하는 처방 일수 표현."""

        if self.days is None:
            return None

        return f"{self.days}일"

    @property
    def administration_instruction(
        self,
    ) -> str | None:
        """기존 프롬프트에서 사용하는 복용 방법."""

        return self.note


class PatientInstruction(BaseModel):
    """사용자가 확인하고 저장한 의료진 권고사항."""

    care_advice_id: int | None = None
    content: str
    display_order: int = Field(default=1, ge=1)

    # 최신 ERD에는 권고사항 유형이 없으므로 선택값으로 처리
    instruction_type: InstructionType | None = None

    # 기존 출처 연결 코드가 사용하는 임시 호환 필드
    source_field_id: int | None = Field(
        default=None,
        exclude=True,
    )


class FollowUpSchedule(BaseModel):
    """외래 진료 또는 검사 일정."""

    follow_up_visit_id: int | None = None
    visit_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "visit_at",
            "scheduled_at",
        ),
    )
    department: str | None = None
    doctor_name: str | None = None
    place: str | None = None
    purpose: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "purpose",
            "description",
        ),
    )

    # 기존 테스트 데이터와 출처 연결을 위한 임시 호환 필드
    institution_name: str | None = Field(
        default=None,
        exclude=True,
    )
    source_field_ids: list[int] = Field(
        default_factory=list,
        exclude=True,
    )

    @property
    def description(self) -> str:
        """기존 프롬프트에서 사용하는 일정 설명."""

        return self.purpose or ""

    @property
    def scheduled_at(self) -> str | None:
        """기존 프롬프트가 JSON으로 전달하는 일정 시각."""

        if self.visit_at is None:
            return None

        return self.visit_at.isoformat()


class PatientContext(BaseModel):
    """LLM과 RAG가 사용하는 확정 환자 정보."""

    user_id: int
    care_episode_id: int

    diagnoses: list[str] = Field(
        default_factory=list
    )
    surgery: str | None = None
    discharge_date: date | None = None
    medication_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
    )
    medication_start_date: date | None = None
    medication_start_slot: str | None = None
    confirmation_hash: str | None = None
    confirmed_at: datetime | None = None

    medications: list[PatientMedication] = Field(
        default_factory=list
    )
    instructions: list[PatientInstruction] = Field(
        default_factory=list
    )
    follow_up_schedules: list[
        FollowUpSchedule
    ] = Field(default_factory=list)
