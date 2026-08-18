from ai_worker.domain.patient_context_hasher import (
    resolve_patient_context_hash,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientMedication,
)


def build_patient_context(
    *,
    dose: str = "1정",
    confirmation_hash: str | None = None,
) -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
        confirmation_hash=confirmation_hash,
        medications=[
            PatientMedication(
                medication_id=101,
                name="아스피린",
                dose=dose,
                times_per_day=1,
                days=7,
                note="아침 식후 복용",
            )
        ],
    )


def test_resolve_uses_confirmed_hash() -> None:
    patient_context = build_patient_context(
        confirmation_hash="a" * 64
    )

    result = resolve_patient_context_hash(
        patient_context
    )

    assert result == "a" * 64


def test_resolve_generates_same_hash_for_same_context() -> None:
    first_context = build_patient_context()
    second_context = build_patient_context()

    first_hash = resolve_patient_context_hash(
        first_context
    )
    second_hash = resolve_patient_context_hash(
        second_context
    )

    assert first_hash == second_hash
    assert len(first_hash) == 64
    assert all(
        character in "0123456789abcdef"
        for character in first_hash
    )


def test_resolve_changes_hash_when_context_changes() -> None:
    first_context = build_patient_context(
        dose="1정"
    )
    second_context = build_patient_context(
        dose="2정"
    )

    assert resolve_patient_context_hash(
        first_context
    ) != resolve_patient_context_hash(
        second_context
    )
