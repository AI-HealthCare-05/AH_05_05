from ai_worker.schemas.patient import FollowUpSchedule


class FollowUpScheduleAnswerAssembler:
    """등록된 진료일정을 짧고 결정적으로 표시한다."""

    @classmethod
    def assemble(cls, schedules: list[FollowUpSchedule]) -> str:
        lines = [cls._format_schedule(schedule) for schedule in schedules]
        lines = [line for line in lines if line is not None]
        if not lines:
            return "등록된 예정 진료일정이 없습니다."
        return "🗓️ **진료 일정**\n" + "\n".join(lines)

    @staticmethod
    def _format_schedule(schedule: FollowUpSchedule) -> str | None:
        if schedule.visit_at is None:
            return None
        date_label = f"{schedule.visit_at.month}월 {schedule.visit_at.day}일"
        time_label = f" {schedule.visit_time:%H:%M}" if schedule.visit_time is not None else ""
        hospital_label = f" · {schedule.hospital}" if schedule.hospital else ""
        return f"- {date_label}{time_label}{hospital_label}"
