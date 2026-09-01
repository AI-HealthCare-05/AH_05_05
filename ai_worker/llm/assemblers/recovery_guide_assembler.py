from ai_worker.domain.patient_fact_formatter import (
    format_patient_medication,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
    RecoveryGuideSupplement,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
)


class RecoveryGuideAssembler:
    """확정 환자정보와 LLM 보충정보를 결합한다."""

    SAFETY_NOTICE = (
        "이 안내는 의료진의 진료를 대체하지 않습니다. "
        "복약 변경이나 증상 판단이 필요한 경우 "
        "의료진 또는 의료기관에 문의하세요."
    )

    def assemble(
        self,
        patient_context: PatientContext,
        supplement: RecoveryGuideSupplement,
    ) -> RecoveryGuideContent:
        instructions = sorted(
            patient_context.instructions,
            key=lambda instruction: (instruction.display_order),
        )

        return RecoveryGuideContent(
            medication_guide=[format_patient_medication(medication) for medication in patient_context.medications],
            patient_instructions=[instruction.content for instruction in instructions],
            public_information=(supplement.public_information),
            lifestyle_guide=(supplement.lifestyle_guide),
            warning_signs=[],
            follow_up_schedule=[self._format_follow_up(schedule) for schedule in patient_context.follow_up_schedules],
            safety_notice=self.SAFETY_NOTICE,
        )

    @staticmethod
    def _format_follow_up(
        schedule: FollowUpSchedule,
    ) -> str:
        parts: list[str] = []

        if schedule.visit_at is not None:
            parts.append(schedule.visit_at.strftime("%Y-%m-%d %H:%M"))

        if schedule.hospital:
            parts.append(schedule.hospital)

        return " · ".join(parts)
