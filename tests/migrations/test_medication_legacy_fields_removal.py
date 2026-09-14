"""Verify the removal SQL and DB consumers using isolated in-memory databases."""

import sqlite3
from datetime import date, datetime
from importlib import import_module

import pytest
from aerich.utils import decompress_dict
from tortoise import Tortoise

from ai_worker.providers.db_active_intake_context_provider import DbActiveIntakeContextProvider
from ai_worker.providers.db_patient_context_provider import DbPatientContextProvider
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import CareEpisode
from app.models.enums import MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User
from app.services.medication_schedule import MedicationScheduleService

MIGRATION = "app.core.db.migrations.models.46_20260914000000_remove_medication_legacy_fields"
PREVIOUS = "app.core.db.migrations.models.45_20260910190000_merge_custom_challenge_finalization_heads"
REMOVED = {"efficacy", "administration", "precautions", "note"}


async def test_registration_schedule_and_ai_context_work_without_legacy_columns():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS})
    try:
        await Tortoise.generate_schemas()
        db = Tortoise.get_connection("default")
        columns = {row["name"] for row in await db.execute_query_dict("PRAGMA table_info(medications)")}
        # Model declarations must not silently hide a reference to an old DB column.
        for column in sorted(REMOVED & columns):
            await db.execute_script(f'ALTER TABLE medications DROP COLUMN "{column}";')
        user = await User.create(email="legacy-removal@example.test", hashed_password="test-only", name="테스트")
        episode = await CareEpisode.create(
            user=user,
            medication_start_date=date(2026, 9, 14),
            medication_days=7,
            confirmation_hash="a" * 64,
            confirmed_at=datetime(2026, 9, 14),
        )
        medication = await Medication.create(
            care_episode=episode, name="테스트 약", strength="10mg", dose_quantity="1정", times_per_day=1, days=7
        )
        await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)

        schedule = await MedicationScheduleService().get(user, episode.id)
        assert schedule.medications[0].name == "테스트 약"
        assert schedule.medications[0].timing == ""
        assert schedule.medications[0].slots == ["morning"]
        active = await DbActiveIntakeContextProvider(today_provider=lambda: date(2026, 9, 14)).get_active_context(
            user_id=user.id, care_episode_id=episode.id
        )
        assert active.medications[0].dose == "1정"
        assert active.medications[0].scheduled_slots == ["MORNING"]
        assert all(getattr(active.medications[0], field) is None for field in REMOVED)
        patient = await DbPatientContextProvider().get_patient_context(user.id, episode.id)
        assert patient.medications[0].name == "테스트 약"
        assert patient.medications[0].note is None
    finally:
        await Tortoise.close_connections()


def _legacy_database():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE medications (
            id BIGINT PRIMARY KEY, name VARCHAR(255), dose_quantity VARCHAR(50),
            efficacy VARCHAR(500), administration VARCHAR(500), precautions VARCHAR(500), note VARCHAR(500)
        );
        INSERT INTO medications VALUES (1, '보존할 약', '0.5정', '효능', '식후', '주의', '기존 메모');
        INSERT INTO medications VALUES (2, '빈 필드 약', '1정', NULL, NULL, NULL, NULL);
        CREATE TABLE medication_notes (id BIGINT PRIMARY KEY, body VARCHAR(500));
        INSERT INTO medication_notes VALUES (1, '사용자 복약 메모 보존');
    """)
    return db


async def test_migration_removes_four_columns_without_creating_a_backup():
    migration = import_module(MIGRATION)
    db = _legacy_database()
    try:
        db.executescript(await migration.upgrade(None))
        assert {row[1] for row in db.execute("PRAGMA table_info(medications)")} == {"id", "name", "dose_quantity"}
        assert db.execute("SELECT * FROM medications ORDER BY id").fetchall() == [
            (1, "보존할 약", "0.5정"),
            (2, "빈 필드 약", "1정"),
        ]
        assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            "medications",
            "medication_notes",
        }
        assert db.execute("SELECT body FROM medication_notes").fetchone() == ("사용자 복약 메모 보존",)
        with pytest.raises(RuntimeError, match="intentionally irreversible"):
            await migration.downgrade(None)
    finally:
        db.close()


def test_migration_snapshot_preserves_other_models_and_matches_medication_columns():
    previous = decompress_dict(import_module(PREVIOUS).MODELS_STATE)
    current = decompress_dict(import_module(MIGRATION).MODELS_STATE)
    for name, model in previous.items():
        if name != "models.Medication":
            assert current[name] == model
    expected = [field for field in previous["models.Medication"]["data_fields"] if field["name"] not in REMOVED]
    assert current["models.Medication"]["data_fields"] == expected
    assert not REMOVED.intersection(Medication._meta.fields_map)
