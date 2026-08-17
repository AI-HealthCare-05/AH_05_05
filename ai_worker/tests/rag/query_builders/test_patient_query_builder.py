from ai_worker.rag.query_builders.patient_query_builder import (
    PatientQueryBuilder,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientMedication,
)


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=987654,
        care_episode_id=123456,
        diagnoses=[
            "뇌졸중",
            "고혈압",
        ],
        medications=[
            PatientMedication(
                entity_key="medication-1",
                drug_name="아스피린",
                dose="1정",
                frequency="1일 1회",
                duration="7일",
                administration_instruction=(
                    "아침 식후 복용"
                ),
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                description="신경과 외래 진료",
                scheduled_at=(
                    "2026-08-20T10:00:00+09:00"
                ),
                institution_name="테스트병원",
            )
        ],
    )


def test_build_medication_search_query() -> None:
    patient_context = build_patient_context()
    builder = PatientQueryBuilder()

    result = builder.build(
        patient_context=patient_context,
        condition=" stroke ",
        topic=" medication ",
        limit=5,
    )

    assert result.condition == "STROKE"
    assert result.care_phase == "POST_DISCHARGE"
    assert result.topic == "MEDICATION"
    assert result.limit == 5

    assert "뇌졸중" in result.query
    assert "고혈압" in result.query
    assert "아스피린" in result.query
    assert "퇴원 후" in result.query
    assert "복약" in result.query


def test_build_excludes_patient_identifiers() -> None:
    patient_context = build_patient_context()
    builder = PatientQueryBuilder()

    result = builder.build(
        patient_context=patient_context,
        condition="STROKE",
        topic="MEDICATION",
    )

    assert "987654" not in result.query
    assert "123456" not in result.query
    assert "테스트병원" not in result.query
    assert "2026-08-20" not in result.query
    assert "1정" not in result.query
    assert "1일 1회" not in result.query
    assert "7일" not in result.query


def test_build_lifestyle_query_excludes_medication() -> None:
    patient_context = build_patient_context()
    builder = PatientQueryBuilder()

    result = builder.build(
        patient_context=patient_context,
        condition="STROKE",
        topic="LIFESTYLE",
    )

    assert "뇌졸중" in result.query
    assert "생활관리" in result.query
    assert "아스피린" not in result.query


def test_build_uses_condition_when_diagnosis_is_empty() -> None:
    patient_context = PatientContext(
        user_id=1,
        care_episode_id=100,
    )
    builder = PatientQueryBuilder()

    result = builder.build(
        patient_context=patient_context,
        condition="COPD",
        topic="LIFESTYLE",
    )

    assert "COPD" in result.query
    assert result.condition == "COPD"
