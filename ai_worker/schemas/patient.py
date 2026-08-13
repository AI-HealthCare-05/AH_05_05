#Core가 사용할 확정 환자 정의(LLM,RAG가 사용할 확정 환자 정보의 내부 표준 구조)

from pydantic import BaseModel, Field

from ai_worker.schemas.enums import InstructionType


class PatientMedication(BaseModel): #투약/복약 정보
    entity_key: str
    drug_name: str
    drug_code: str | None = None

    dose: str | None = None
    frequency: str | None = None
    duration: str | None = None
    administration_instruction: str | None = None

    source_field_ids: list[int] = Field(default_factory=list)


class PatientInstruction(BaseModel): #환자 안내/지침 정보
    instruction_type: InstructionType
    content: str
    source_field_id: int | None = None


class FollowUpSchedule(BaseModel): #추적 관찰/재진 일정
    description: str
    scheduled_at: str | None = None
    institution_name: str | None = None
    source_field_ids: list[int] = Field(default_factory=list)


class PatientContext(BaseModel): #최종 확정 환자 컨텍스트
    user_id: int
    care_episode_id: int

    diagnoses: list[str] = Field(default_factory=list)
    medications: list[PatientMedication] = Field(default_factory=list)
    instructions: list[PatientInstruction] = Field(default_factory=list)
    follow_up_schedules: list[FollowUpSchedule] = Field(default_factory=list)