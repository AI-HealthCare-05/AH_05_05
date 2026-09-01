from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ai_worker.domain.errors import (
    PatientContextNotFoundError,
    UnconfirmedPatientContextError,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientInstruction,
    PatientMedication,
)
from app.models.care import (
    CareAdvice,
    CareEpisode,
    FollowUpVisit,
)
from app.models.medications import Medication


class DbPatientContextProvider:
    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        care_episode = await CareEpisode.filter(
            id=care_episode_id,
            user_id=user_id,
        ).first()

        if care_episode is None:
            raise PatientContextNotFoundError("요청한 사용자의 케어 에피소드를 찾을 수 없습니다.")

        if care_episode.confirmed_at is None or not care_episode.confirmation_hash:
            raise UnconfirmedPatientContextError("사용자가 확인하고 저장한 확정 환자정보가 아닙니다.")

        medications = await Medication.filter(
            care_episode_id=care_episode_id,
        ).order_by("id")

        care_advices = await CareAdvice.filter(
            care_episode_id=care_episode_id,
        ).order_by(
            "display_order",
            "id",
        )

        follow_up_visits = await FollowUpVisit.filter(
            user_id=user_id,
        ).order_by(
            "visit_date",
            "visit_time",
            "id",
        )

        return PatientContext(
            user_id=user_id,
            care_episode_id=care_episode.id,
            diagnoses=self._build_diagnoses(care_episode.diagnosis),
            surgery=care_episode.surgery,
            discharge_date=care_episode.discharge_date,
            medication_days=(care_episode.medication_days),
            medication_start_date=(care_episode.medication_start_date),
            medication_start_slot=(self._resolve_enum_value(care_episode.medication_start_slot)),
            confirmation_hash=(care_episode.confirmation_hash),
            confirmed_at=care_episode.confirmed_at,
            medications=[
                PatientMedication(
                    medication_id=medication.id,
                    name=medication.name,
                    dose=medication.dose_quantity,
                    times_per_day=(medication.times_per_day),
                    note=medication.note,
                    days=medication.days,
                    prescribed_at=(medication.prescribed_at),
                )
                for medication in medications
            ],
            instructions=[
                PatientInstruction(
                    care_advice_id=care_advice.id,
                    content=care_advice.text,
                    display_order=(care_advice.display_order),
                )
                for care_advice in care_advices
            ],
            follow_up_schedules=[
                FollowUpSchedule(
                    follow_up_visit_id=visit.id,
                    visit_at=self._combine_visit_at(
                        visit_date=visit.visit_date,
                        visit_time=visit.visit_time,
                    ),
                    hospital=visit.hospital,
                )
                for visit in follow_up_visits
            ],
        )

    @staticmethod
    def _combine_visit_at(
        visit_date: date,
        visit_time: time | None,
    ) -> datetime:
        return datetime.combine(
            visit_date,
            visit_time or time.min,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )

    @staticmethod
    def _build_diagnoses(
        diagnosis: str | None,
    ) -> list[str]:
        if diagnosis is None:
            return []

        normalized = diagnosis.strip()

        if not normalized:
            return []

        return [normalized]

    @staticmethod
    def _resolve_enum_value(
        value: object | None,
    ) -> str | None:
        if value is None:
            return None

        enum_value = getattr(
            value,
            "value",
            value,
        )

        return str(enum_value)
