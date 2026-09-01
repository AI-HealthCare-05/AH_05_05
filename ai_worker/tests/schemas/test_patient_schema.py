from datetime import date, datetime

from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientInstruction,
    PatientMedication,
)


def test_patient_context_represents_confirmed_erd_data() -> None:
    context = PatientContext(
        user_id=1,
        care_episode_id=10,
        diagnoses=["고관절 골절"],
        surgery="고관절 수술",
        discharge_date=date(2026, 8, 10),
        medication_days=7,
        medication_start_date=date(2026, 8, 11),
        medication_start_slot="MORNING",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(2026, 8, 11, 10, 30),
        medications=[
            PatientMedication(
                medication_id=101,
                name="테스트정",
                dose="200mg",
                times_per_day=2,
                note="아침·저녁 식후 복용",
                days=7,
                prescribed_at=date(2026, 8, 10),
            )
        ],
        instructions=[
            PatientInstruction(
                care_advice_id=201,
                content="퇴원 후 무리한 활동을 피하세요.",
                display_order=1,
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                follow_up_visit_id=301,
                visit_at=datetime(2026, 8, 20, 10, 0),
                hospital="테스트병원",
            )
        ],
    )

    assert context.surgery == "고관절 수술"
    assert context.discharge_date == date(2026, 8, 10)
    assert context.medication_days == 7
    assert context.medication_start_date == date(2026, 8, 11)
    assert context.medication_start_slot == "MORNING"
    assert context.confirmation_hash == "a" * 64
    assert context.confirmed_at == datetime(
        2026,
        8,
        11,
        10,
        30,
    )

    medication = context.medications[0]
    assert medication.medication_id == 101
    assert medication.name == "테스트정"
    assert medication.times_per_day == 2
    assert medication.note == "아침·저녁 식후 복용"
    assert medication.days == 7

    instruction = context.instructions[0]
    assert instruction.care_advice_id == 201
    assert instruction.content == ("퇴원 후 무리한 활동을 피하세요.")
    assert instruction.display_order == 1
    assert instruction.instruction_type is None

    follow_up = context.follow_up_schedules[0]
    assert follow_up.follow_up_visit_id == 301
    assert follow_up.hospital == "테스트병원"
