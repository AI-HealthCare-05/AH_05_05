from ai_worker.schemas.patient import (
    PatientMedication,
)


def format_patient_medication(
    medication: PatientMedication,
) -> str:
    """확정 복약정보를 사용자 표시 문장으로 변환한다."""

    parts = [medication.name]

    if medication.dose:
        parts.append(medication.dose)

    if medication.times_per_day is not None:
        parts.append(f"1일 {medication.times_per_day}회")

    if medication.note:
        parts.append(medication.note)

    if medication.days is not None:
        parts.append(f"{medication.days}일")

    return " · ".join(parts)
