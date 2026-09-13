from datetime import date
from types import SimpleNamespace

from app.models.enums import CareEpisodeStatus
from app.services.medications import can_create_medication_note


def episode(*, start: date | None, status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE, days: int | None = None):
    return SimpleNamespace(
        medication_start_date=start,
        medication_days=days,
        status=status,
    )


def medication(*, days: int | None, times_per_day: int | None = 1):
    return SimpleNamespace(days=days, times_per_day=times_per_day)


def test_note_creation_period_includes_the_first_and_last_intake_days() -> None:
    prescription = episode(start=date(2026, 9, 11))
    medications = [medication(days=3)]

    assert can_create_medication_note(prescription, medications, date(2026, 9, 11)) is True
    assert can_create_medication_note(prescription, medications, date(2026, 9, 13)) is True


def test_note_creation_period_excludes_before_after_and_non_active_episodes() -> None:
    medications = [medication(days=3)]

    assert can_create_medication_note(
        episode(start=date(2026, 9, 11)), medications, date(2026, 9, 10)
    ) is False
    assert can_create_medication_note(
        episode(start=date(2026, 9, 11)), medications, date(2026, 9, 14)
    ) is False
    assert can_create_medication_note(
        episode(start=date(2026, 9, 11), status=CareEpisodeStatus.COMPLETED),
        medications,
        date(2026, 9, 12),
    ) is False
    assert can_create_medication_note(
        episode(start=date(2026, 9, 11), status=CareEpisodeStatus.CANCELLED),
        medications,
        date(2026, 9, 12),
    ) is False


def test_note_creation_requires_a_known_period_with_at_least_one_medication() -> None:
    assert can_create_medication_note(episode(start=None), [medication(days=3)], date(2026, 9, 13)) is False
    assert can_create_medication_note(episode(start=date(2026, 9, 13)), [], date(2026, 9, 13)) is False
