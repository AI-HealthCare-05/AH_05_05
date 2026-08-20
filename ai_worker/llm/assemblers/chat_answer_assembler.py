from ai_worker.domain.patient_fact_formatter import (
    format_patient_medication,
)
from ai_worker.schemas.chat import (
    ChatAnswerSupplement,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRoute,
    InstructionType,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
)


class ChatAnswerAssembler:
    SAFETY_NOTICE = (
        "이 안내는 의료진의 진료를 대체하지 않습니다. "
        "복약 변경이나 증상 판단이 필요한 경우 "
        "의료진 또는 의료기관에 문의하세요."
    )

    def assemble(
        self,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        supplement: ChatAnswerSupplement,
    ) -> str:
        sections: list[str] = []

        patient_lines = self._build_patient_lines(
            patient_context=patient_context,
            intent=classification.intent,
        )
        self._append_section(
            sections=sections,
            title="환자 확정정보",
            lines=patient_lines,
        )

        if classification.intent == ChatIntent.GENERAL:
            self._append_section(
                sections=sections,
                title="안내",
                lines=supplement.general_response,
            )

        if classification.route == ChatRoute.PATIENT_AND_RAG:
            self._append_section(
                sections=sections,
                title="공공자료 추가 설명",
                lines=supplement.public_information,
            )

        if classification.intent == ChatIntent.LIFESTYLE:
            self._append_section(
                sections=sections,
                title="AI 생성 일반 안내",
                lines=supplement.lifestyle_guidance,
            )

        sections.append(self.SAFETY_NOTICE)

        return "\n\n".join(sections)

    @classmethod
    def _build_patient_lines(
        cls,
        patient_context: PatientContext,
        intent: ChatIntent,
    ) -> list[str]:
        if intent == ChatIntent.PATIENT_FACT:
            return cls._build_patient_fact_lines(patient_context)

        if intent == ChatIntent.MEDICATION:
            return [format_patient_medication(medication) for medication in (patient_context.medications)]

        if intent == ChatIntent.FOLLOW_UP:
            return [
                formatted
                for schedule in (patient_context.follow_up_schedules)
                if (formatted := cls._format_follow_up(schedule))
            ]

        if intent == ChatIntent.LIFESTYLE:
            instructions = sorted(
                patient_context.instructions,
                key=lambda instruction: (instruction.display_order),
            )
            return [instruction.content for instruction in instructions]

        if intent == ChatIntent.WARNING_SIGN:
            return [
                instruction.content
                for instruction in (patient_context.instructions)
                if (instruction.instruction_type == InstructionType.WARNING_SIGN)
            ]

        return []

    @staticmethod
    def _build_patient_fact_lines(
        patient_context: PatientContext,
    ) -> list[str]:
        lines: list[str] = []

        if patient_context.diagnoses:
            lines.append("진단명: " + ", ".join(patient_context.diagnoses))

        if patient_context.surgery:
            lines.append(f"수술/시술: {patient_context.surgery}")

        if patient_context.discharge_date:
            lines.append(f"퇴원일: {patient_context.discharge_date.isoformat()}")

        return lines

    @staticmethod
    def _format_follow_up(
        schedule: FollowUpSchedule,
    ) -> str:
        parts: list[str] = []

        if schedule.visit_at is not None:
            parts.append(schedule.visit_at.strftime("%Y-%m-%d %H:%M"))

        if schedule.department:
            parts.append(schedule.department)

        if schedule.doctor_name:
            parts.append(schedule.doctor_name)

        if schedule.purpose:
            parts.append(schedule.purpose)

        place = schedule.place or schedule.institution_name
        if place:
            parts.append(place)

        return " · ".join(parts)

    @staticmethod
    def _append_section(
        sections: list[str],
        title: str,
        lines: list[str],
    ) -> None:
        normalized_lines = [line.strip() for line in lines if line.strip()]

        if not normalized_lines:
            return

        body = "\n".join(f"- {line}" for line in normalized_lines)
        sections.append(f"{title}\n{body}")
