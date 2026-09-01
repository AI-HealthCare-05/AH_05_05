from datetime import date, datetime

from ai_worker.domain.chat_source_builder import ChatSourceBuilder
from ai_worker.schemas.enums import (
    CareEpisodeSourceField,
    ChatIntent,
    PatientSourceKind,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientInstruction,
)


def test_build_patient_sources_tracks_rendered_patient_records() -> None:
    patient_context = PatientContext(
        user_id=1,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
        surgery="혈관 내 치료",
        discharge_date=date(2026, 8, 10),
        confirmation_hash="a" * 64,
        instructions=[
            PatientInstruction(
                care_advice_id=201,
                content="무리한 활동을 피하세요.",
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

    patient_fact_sources = ChatSourceBuilder.build_patient_sources(
        patient_context=patient_context,
        intent=ChatIntent.PATIENT_FACT,
    )
    lifestyle_sources = ChatSourceBuilder.build_patient_sources(
        patient_context=patient_context,
        intent=ChatIntent.LIFESTYLE,
    )
    follow_up_sources = ChatSourceBuilder.build_patient_sources(
        patient_context=patient_context,
        intent=ChatIntent.FOLLOW_UP,
    )

    assert [source.patient_field for source in patient_fact_sources] == [
        CareEpisodeSourceField.DIAGNOSIS,
        CareEpisodeSourceField.SURGERY,
        CareEpisodeSourceField.DISCHARGE_DATE,
    ]
    assert lifestyle_sources[0].patient_source_kind == (PatientSourceKind.CARE_ADVICE)
    assert lifestyle_sources[0].care_advice_id == 201
    assert follow_up_sources[0].patient_source_kind == (PatientSourceKind.FOLLOW_UP_VISIT)
    assert follow_up_sources[0].follow_up_visit_id == 301
