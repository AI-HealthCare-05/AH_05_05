from datetime import date, datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.providers.db_medication_note_summary_provider import (
    DbMedicationNoteSummaryProvider,
)
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus
from app.models.medications import Medication, MedicationNote
from app.models.users import User


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _create_episode(
    *,
    user: User,
    alias: str,
    status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE,
) -> CareEpisode:
    return await CareEpisode.create(
        user=user,
        alias=alias,
        status=status,
    )


async def _create_note(
    *,
    user: User,
    episode: CareEpisode,
    body: str,
    dosed_at: datetime,
    medication: Medication | None = None,
) -> MedicationNote:
    return await MedicationNote.create(
        user=user,
        care_episode=episode,
        medication=medication,
        body=body,
        dosed_at=dosed_at,
    )


@pytest.mark.asyncio
async def test_recent_scope_groups_owned_notes_by_episode_and_keeps_unlinked_notes(
    initialized_db: None,
) -> None:
    owner = await User.create(
        email="owner@example.com",
        hashed_password="hashed-password",
        name="소유자",
    )
    other_user = await User.create(
        email="other@example.com",
        hashed_password="hashed-password",
        name="다른 사용자",
    )
    newer_episode = await _create_episode(user=owner, alias="최근 진료")
    older_episode = await _create_episode(
        user=owner,
        alias="종료 진료",
        status=CareEpisodeStatus.COMPLETED,
    )
    other_episode = await _create_episode(user=other_user, alias="다른 사용자 진료")
    medication = await Medication.create(
        care_episode=newer_episode,
        name="타이레놀정",
    )
    await _create_note(
        user=owner,
        episode=newer_episode,
        medication=medication,
        body="두통이 지속됨",
        dosed_at=datetime(2026, 9, 3, 9, 0),
    )
    await _create_note(
        user=owner,
        episode=newer_episode,
        body="속쓰림이 있었음",
        dosed_at=datetime(2026, 9, 4, 9, 0),
    )
    await _create_note(
        user=owner,
        episode=older_episode,
        body="멍이 쉽게 듦",
        dosed_at=datetime(2026, 8, 20, 9, 0),
    )
    await _create_note(
        user=other_user,
        episode=other_episode,
        body="다른 사용자의 메모",
        dosed_at=datetime(2026, 9, 10, 9, 0),
    )

    selection = await DbMedicationNoteSummaryProvider(
        today_provider=lambda: date(2026, 9, 11),
    ).list_episodes(
        user_id=owner.id,
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
    )

    assert [episode.care_episode_id for episode in selection.episodes] == [
        newer_episode.id,
        older_episode.id,
    ]
    assert [note.body for note in selection.episodes[0].notes] == [
        "두통이 지속됨",
        "속쓰림이 있었음",
    ]
    assert selection.episodes[0].notes[0].medication_name == "타이레놀정"
    assert selection.episodes[0].notes[1].medication_name is None


@pytest.mark.asyncio
async def test_recent_scope_returns_three_latest_episodes_and_marks_more(
    initialized_db: None,
) -> None:
    owner = await User.create(
        email="owner@example.com",
        hashed_password="hashed-password",
        name="소유자",
    )
    episodes = [await _create_episode(user=owner, alias=f"진료 {index}") for index in range(1, 5)]
    for index, episode in enumerate(episodes, start=1):
        await _create_note(
            user=owner,
            episode=episode,
            body=f"메모 {index}",
            dosed_at=datetime(2026, 8, index, 9, 0),
        )

    selection = await DbMedicationNoteSummaryProvider(
        today_provider=lambda: date(2026, 9, 11),
    ).list_episodes(
        user_id=owner.id,
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
    )

    assert [episode.care_episode_id for episode in selection.episodes] == [
        episodes[3].id,
        episodes[2].id,
        episodes[1].id,
    ]
    assert selection.has_more_episodes is True


@pytest.mark.asyncio
async def test_all_history_scope_includes_completed_episode_before_six_month_cutoff(
    initialized_db: None,
) -> None:
    owner = await User.create(
        email="owner@example.com",
        hashed_password="hashed-password",
        name="소유자",
    )
    old_completed_episode = await _create_episode(
        user=owner,
        alias="과거 종료 진료",
        status=CareEpisodeStatus.COMPLETED,
    )
    cancelled_episode = await _create_episode(
        user=owner,
        alias="취소 진료",
        status=CareEpisodeStatus.CANCELLED,
    )
    await _create_note(
        user=owner,
        episode=old_completed_episode,
        body="과거 메모",
        dosed_at=datetime(2025, 1, 3, 9, 0),
    )
    await _create_note(
        user=owner,
        episode=cancelled_episode,
        body="제외할 메모",
        dosed_at=datetime(2026, 9, 1, 9, 0),
    )

    selection = await DbMedicationNoteSummaryProvider(
        today_provider=lambda: date(2026, 9, 11),
    ).list_episodes(
        user_id=owner.id,
        scope=MedicationNoteSummaryScope.ALL_HISTORY,
    )

    assert [episode.care_episode_id for episode in selection.episodes] == [
        old_completed_episode.id,
    ]
