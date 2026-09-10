"""Bounded #315 verification against app.main and a disposable real MySQL schema.

Run this module with ``--noconftest``.  It deliberately does not use the shared
SQLite test harness and never overrides ``get_request_user``.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import asyncmy
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise
from tortoise.backends.mysql.client import TransactionWrapper

if os.getenv("TEST315_RUN_MYSQL") != "1":
    pytest.skip("set TEST315_RUN_MYSQL=1 for the dedicated #315 MySQL integration run", allow_module_level=True)

MYSQL_HOST = os.getenv("TEST315_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("TEST315_MYSQL_PORT", "3315"))
MYSQL_USER = os.getenv("TEST315_MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("TEST315_MYSQL_PASSWORD", "migration315")
MYSQL_BOOTSTRAP_DB = os.getenv("TEST315_MYSQL_BOOTSTRAP_DB", "migration315_bootstrap")
MYSQL_DATABASE = f"test315_api_{os.getpid()}_{uuid4().hex[:10]}"
assert re.fullmatch(r"[a-z0-9_]+", MYSQL_DATABASE)
assert MYSQL_PORT == 3315, "This suite is restricted to the disposable #315 MySQL port"

# app.core.config and the JWT backend are instantiated during module import.
os.environ.update(
    {
        "DB_HOST": MYSQL_HOST,
        "DB_PORT": str(MYSQL_PORT),
        "DB_USER": MYSQL_USER,
        "DB_PASSWORD": MYSQL_PASSWORD,
        "DB_NAME": MYSQL_DATABASE,
        "SECRET_KEY": "test315-real-jwt-signing-key",
    }
)

from app.core import config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.care import CareEpisode  # noqa: E402
from app.models.challenges import CustomChallengeTemplate  # noqa: E402
from app.models.custom_challenges import (  # noqa: E402
    CustomChallengeBadgeAward,
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (  # noqa: E402
    AccountStatus,
    CareEpisodeStatus,
    ChallengeParticipationStatus,
    CustomChallengeType,
    MealSlot,
    SupplementStatus,
)
from app.models.medications import Medication, MedicationDose, MedicationSlot  # noqa: E402
from app.models.supplement_nutrients import (  # noqa: E402
    SupplementDose,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import User  # noqa: E402
from app.services import custom_challenges as custom_challenge_module  # noqa: E402
from app.services import medications as medication_module  # noqa: E402
from app.services import supplement_doses as supplement_dose_module  # noqa: E402

PASSWORD = "Password123!"
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _server_statement(statement: str) -> None:
    connection = await asyncmy.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_BOOTSTRAP_DB,
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(statement)
    finally:
        connection.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def isolated_mysql_schema() -> None:
    """Create and finally drop only this run's current-model MySQL database.

    Blank-to-head Aerich is intentionally not used: immutable legacy migration 4
    returns empty SQL on MySQL. Migration 43 has its own isolated 42-to-43 test;
    this suite owns the real application/API behavior on the current model schema.
    """

    await _server_statement(f"CREATE DATABASE `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    try:
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas(safe=True)
        connection = Tortoise.get_connection("default")
        # Reproduce the immutable reference-data path needed by migration 42.
        # Current-model schema generation creates tables only, not these rows.
        for module_name in (
            "app.core.db.migrations.models.38_20260908132414_seed_custom_challenge_defaults",
            "app.core.db.migrations.models.40_20260909000000_rename_custom_challenge_check_type_group",
            "app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads",
        ):
            seed_migration = import_module(module_name)
            await connection.execute_script(await seed_migration.upgrade(connection))
        database_row = (await connection.execute_query_dict("SELECT DATABASE() AS database_name"))[0]
        assert database_row["database_name"] == MYSQL_DATABASE
        engines = await connection.execute_query_dict(
            "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
            "('custom_challenge_participations', 'custom_challenge_occurrences', "
            "'custom_challenge_badge_awards', 'medication_doses', 'supplement_doses')"
        )
        assert {row["TABLE_NAME"]: row["ENGINE"] for row in engines} == {
            "custom_challenge_badge_awards": "InnoDB",
            "custom_challenge_occurrences": "InnoDB",
            "custom_challenge_participations": "InnoDB",
            "medication_doses": "InnoDB",
            "supplement_doses": "InnoDB",
        }
        assert not app.dependency_overrides
        yield
    finally:
        if Tortoise._inited:  # noqa: SLF001
            await Tortoise.close_connections()
        await _server_statement(f"DROP DATABASE IF EXISTS `{MYSQL_DATABASE}`")


class _FixedDateTime(datetime):
    current: datetime

    @classmethod
    def now(cls, tz=None) -> datetime:  # noqa: ANN001
        current = cls.current
        if tz is None:
            return current.replace(tzinfo=None)
        return current.astimezone(tz)


@contextmanager
def _controlled_api_clock(at: datetime, *modules):  # noqa: ANN001, ANN202
    """Control only the production modules' clocks; no endpoint/service is stubbed."""

    _FixedDateTime.current = at
    with ExitStack() as stack:
        for module in modules:
            stack.enter_context(patch.object(module, "datetime", _FixedDateTime))
        yield


async def _create_user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password=hash_password(PASSWORD),
        name="MySQL 통합 사용자",
        status=AccountStatus.ACTIVE,
    )


async def _auth_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _template(challenge_type: CustomChallengeType) -> CustomChallengeTemplate:
    template = await (
        CustomChallengeTemplate.filter(
            is_active=True,
            challenge_type__detail_code=challenge_type.value,
        )
        .prefetch_related("reward_badge")
        .first()
    )
    assert template is not None
    assert template.reward_badge_id is not None
    return template


async def _episode(user: User, alias: str, start_at: datetime, days: int = 9) -> CareEpisode:
    episode = await CareEpisode.create(
        user=user,
        alias=alias,
        status=CareEpisodeStatus.ACTIVE,
        medication_start_date=start_at.date(),
        medication_start_slot=MealSlot.MORNING,
        medication_days=days,
    )
    medication = await Medication.create(
        care_episode=episode,
        name=f"{alias} 약",
        times_per_day=1,
        days=days,
    )
    await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)
    return episode


async def _recommendation(
    client: AsyncClient,
    headers: dict[str, str],
    challenge_type: CustomChallengeType,
) -> dict:
    response = await client.get("/api/v1/user/custom-challenge-recommendations", headers=headers)
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["challengeType"] == challenge_type.value)


async def _claim(client: AsyncClient, headers: dict[str, str], participation_id: int) -> dict:
    response = await client.post(
        f"/api/v1/user/custom-challenge-participations/{participation_id}/claim-reward",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"participation", "award", "newlyAwarded"}
    return payload


async def _active_claim_case(client: AsyncClient, kind: CustomChallengeType) -> tuple:
    """One actual scheduled goal, saved through the authenticated dose endpoint."""
    now = datetime.now(config.TIMEZONE)
    user = await _create_user(f"claim-{uuid4().hex}@example.com")
    headers = await _auth_headers(client, user.email)
    template = await _template(kind)
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge_id=template.reward_badge_id,
        challenge_type=kind,
        challenge_name="동시 수령 검증",
        idempotency_key=uuid4().hex,
        joined_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=2),
    )
    scheduled_at = now - timedelta(minutes=1)
    if kind is CustomChallengeType.MEDICATION:
        episode = await _episode(user, "수령 경계 처방", scheduled_at, days=2)
        target = await CustomChallengeTarget.create(
            participation=participation,
            care_episode=episode,
            source_id_snapshot=episode.id,
            target_name_snapshot=episode.alias,
        )
        dose_method, dose_path = "POST", "/api/v1/medications/doses"
        dose_payload = {"recordId": episode.id, "date": scheduled_at.date().isoformat(), "slot": "morning"}
    else:
        registration = await UserSupplementNutrient.create(
            user=user,
            custom_name="수령 경계 영양제",
            dose_amount=Decimal("1"),
            dose_unit="정",
            start_date=scheduled_at.date(),
            status=SupplementStatus.ACTIVE,
        )
        await UserSupplementNutrientSlot.create(user_suppl_nutrient=registration, slot=MealSlot.MORNING)
        target = await CustomChallengeTarget.create(
            participation=participation,
            supplement_registration=registration,
            source_id_snapshot=registration.id,
            target_name_snapshot=registration.custom_name,
        )
        dose_method, dose_path = "PUT", "/api/v1/med/supplement-doses"
        dose_payload = {
            "supplementId": registration.id,
            "date": scheduled_at.date().isoformat(),
            "slot": "morning",
        }
    occurrence = await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=scheduled_at.date(),
        slot=MealSlot.MORNING,
        scheduled_at=scheduled_at,
    )
    saved = await client.request(dose_method, dose_path, headers=headers, json={**dose_payload, "taken": True})
    assert saved.status_code == 200, saved.text
    return user, headers, participation, occurrence, dose_method, dose_path, dose_payload


async def _overlap_at_user_lock(first_request, second_request) -> tuple:
    """Pause the first real transaction holding User; let the second contend.

    Only timing is instrumented at the driver boundary. Every SQL call executes
    the original MySQL method, with unmodified arguments/results. No transaction,
    authentication, service, or database response is replaced.
    """
    first_locked, second_attempted, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = TransactionWrapper.execute_query
    first_task = second_task = None

    async def observed(connection, query, *args, **kwargs):
        is_user_lock = "FOR UPDATE" in query.upper() and "`user`" in query
        task = asyncio.current_task()
        if is_user_lock and task is second_task:
            second_attempted.set()
        result = await original(connection, query, *args, **kwargs)
        if is_user_lock and task is first_task and not first_locked.is_set():
            first_locked.set()
            await release.wait()
        return result

    async def reached(event, task):
        waiter = asyncio.create_task(event.wait())
        try:
            done, _ = await asyncio.wait({waiter, task}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                response = task.result()
                pytest.fail(f"Request finished without the expected User lock: {response.status_code} {response.text}")
            assert waiter in done, "Request never reached its real User SELECT FOR UPDATE"
        finally:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

    with patch.object(TransactionWrapper, "execute_query", observed):
        try:
            first_task = asyncio.create_task(first_request)
            await reached(first_locked, first_task)
            second_task = asyncio.create_task(second_request)
            await reached(second_attempted, second_task)
            assert not first_task.done() and not second_task.done()
            release.set()
            return tuple(await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=15))
        finally:
            release.set()
            for task in (first_task, second_task):
                if task is not None and not task.done():
                    task.cancel()
            if second_task is None:
                second_request.close()
            await asyncio.gather(
                *(task for task in (first_task, second_task) if task is not None), return_exceptions=True
            )


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
async def test_active_undo_before_claim_removes_eligibility_and_reads_never_award(kind) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user, headers, participation, occurrence, method, path, payload = await _active_claim_case(client, kind)
        detail_path = f"/api/v1/user/custom-challenge-participations/{participation.id}"
        detail = await client.get(detail_path, headers=headers)
        listed = await client.get("/api/v1/user/custom-challenge-participations", headers=headers)
        badges = await client.get("/api/v1/user/custom-challenges/badges", headers=headers)
        assert detail.status_code == listed.status_code == badges.status_code == 200
        assert detail.json()["status"] == "ACTIVE"
        assert detail.json()["completedCount"] == 1
        assert badges.json() == {"items": [], "totalCount": 0}
        assert await CustomChallengeBadgeAward.filter(user=user).count() == 0
        undone = await client.request(method, path, headers=headers, json={**payload, "taken": False})
        assert undone.status_code == 200, undone.text
        result = await _claim(client, headers, participation.id)
        assert result["award"] is None and result["newlyAwarded"] is False
        assert result["participation"]["status"] == "ACTIVE"
        assert result["participation"]["completedCount"] == 0
        assert result["participation"]["completedDayCount"] == 0
        assert result["participation"]["occurrences"][0]["isCompleted"] is False
        await participation.refresh_from_db()
        assert participation.finalized_at is None
        assert await CustomChallengeBadgeAward.filter(user=user).count() == 0
        foreign = await _create_user(f"foreign-{uuid4().hex}@example.com")
        foreign_headers = await _auth_headers(client, foreign.email)
        denied = await client.post(f"{detail_path}/claim-reward", headers=foreign_headers)
        assert denied.status_code == 404


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
async def test_concurrent_duplicate_claims_award_once_on_real_mysql(kind) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user, headers, participation, occurrence, method, path, payload = await _active_claim_case(client, kind)
        claim_path = f"/api/v1/user/custom-challenge-participations/{participation.id}/claim-reward"
        first, second = await _overlap_at_user_lock(
            client.post(claim_path, headers=headers), client.post(claim_path, headers=headers)
        )
        assert first.status_code == second.status_code == 200, (first.text, second.text)
        assert first.json()["newlyAwarded"] is True
        assert second.json()["newlyAwarded"] is False
        assert first.json()["award"] == second.json()["award"]
        assert first.json()["participation"] == second.json()["participation"]
        await participation.refresh_from_db()
        await occurrence.refresh_from_db()
        assert participation.status is ChallengeParticipationStatus.COMPLETED
        assert participation.finalized_at < participation.end_at
        assert (participation.target_count, participation.completed_count) == (1, 1)
        assert occurrence.is_completed is True
        assert await CustomChallengeBadgeAward.filter(user=user, participation=participation).count() == 1


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.parametrize("claim_first", [True, False], ids=["claim-holds-lock", "undo-holds-lock"])
async def test_claim_and_active_dose_undo_serialize_in_both_orders(kind, claim_first) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user, headers, participation, occurrence, method, path, payload = await _active_claim_case(client, kind)
        claim_request = client.post(
            f"/api/v1/user/custom-challenge-participations/{participation.id}/claim-reward", headers=headers
        )
        undo_request = client.request(method, path, headers=headers, json={**payload, "taken": False})
        responses = await _overlap_at_user_lock(
            *((claim_request, undo_request) if claim_first else (undo_request, claim_request))
        )
        claim_response, undo_response = responses if claim_first else responses[::-1]
        assert claim_response.status_code == undo_response.status_code == 200, (claim_response.text, undo_response.text)
        result = claim_response.json()
        detail = await client.get(f"/api/v1/user/custom-challenge-participations/{participation.id}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json() == result["participation"]
        assert detail.json()["completedCount"] == int(claim_first)
        assert detail.json()["completedDayCount"] == int(claim_first)
        assert detail.json()["occurrences"][0]["isCompleted"] is claim_first
        assert result["newlyAwarded"] is claim_first
        assert (result["award"] is not None) is claim_first
        assert await CustomChallengeBadgeAward.filter(user=user).count() == int(claim_first)
        await participation.refresh_from_db()
        assert (participation.finalized_at is not None) is claim_first
        assert participation.status is (
            ChallengeParticipationStatus.COMPLETED if claim_first else ChallengeParticipationStatus.ACTIVE
        )
        if kind is CustomChallengeType.MEDICATION:
            assert await MedicationDose.filter(user=user).count() == 0
        else:
            assert await SupplementDose.filter(registration__user=user).count() == 0
        replay = await _claim(client, headers, participation.id)
        assert replay["newlyAwarded"] is False
        assert replay["award"] == result["award"]


async def test_medication_api_keeps_episode_results_and_badge_frozen_after_end_and_undo() -> None:
    """Catches cross-episode progress, seven-day truncation, replay, and mutable final snapshots."""

    real_now = datetime.now(config.TIMEZONE)
    joined_at = (real_now - timedelta(days=10)).replace(hour=7, minute=0, second=0, microsecond=0)
    mutation_at = (real_now - timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
    owner = await _create_user("mysql315-med-owner@example.com")
    other = await _create_user("mysql315-med-other@example.com")
    first_episode = await _episode(owner, "9일 첫 처방", joined_at)
    second_episode = await _episode(owner, "9일 둘째 처방", joined_at)
    other_episode = await _episode(other, "타인 처방", joined_at)
    template = await _template(CustomChallengeType.MEDICATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/api/v1/user/custom-challenge-recommendations")
        assert unauthenticated.status_code == 401
        owner_headers = await _auth_headers(client, owner.email)
        other_headers = await _auth_headers(client, other.email)

        with _controlled_api_clock(joined_at, custom_challenge_module):
            recommendation = await _recommendation(client, owner_headers, CustomChallengeType.MEDICATION)
            assert [target["id"] for target in recommendation["targets"]] == [first_episode.id, second_episode.id]

            combined = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=owner_headers,
                json={"targetIds": [first_episode.id, second_episode.id], "idempotencyKey": "combined"},
            )
            assert combined.status_code == 422

            foreign = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=owner_headers,
                json={"targetIds": [other_episode.id], "idempotencyKey": "foreign"},
            )
            assert foreign.status_code == 422

            first_payload = {"targetIds": [first_episode.id], "idempotencyKey": "mysql-first-episode"}
            first_join = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=owner_headers,
                json=first_payload,
            )
            first_replay = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=owner_headers,
                json=first_payload,
            )
            second_join = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=owner_headers,
                json={"targetIds": [second_episode.id], "idempotencyKey": "mysql-second-episode"},
            )

        assert first_join.status_code == first_replay.status_code == second_join.status_code == 201
        assert first_replay.json() == first_join.json()
        first_id = first_join.json()["id"]
        second_id = second_join.json()["id"]
        assert first_id != second_id
        assert first_join.json()["targetCount"] == second_join.json()["targetCount"] == 9
        assert await CustomChallengeParticipation.filter(user=owner).count() == 2
        assert await CustomChallengeTarget.filter(participation_id=first_id).count() == 1
        assert await CustomChallengeOccurrence.filter(target__participation_id=first_id).count() == 9

        first_occurrences = first_join.json()["occurrences"]
        with _controlled_api_clock(mutation_at, medication_module):
            for occurrence in first_occurrences:
                saved = await client.post(
                    "/api/v1/medications/doses",
                    headers=owner_headers,
                    json={
                        "date": occurrence["scheduledDate"],
                        "slot": occurrence["slot"].lower(),
                        "taken": True,
                        "recordId": first_episode.id,
                    },
                )
                assert saved.status_code == 200, saved.text

        assert await MedicationDose.filter(user=owner, care_episode=first_episode).count() == 9
        forbidden_detail = await client.get(
            f"/api/v1/user/custom-challenge-participations/{first_id}", headers=other_headers
        )
        assert forbidden_detail.status_code == 404

        zero_goal = await CustomChallengeParticipation.create(
            user=owner,
            template=template,
            reward_badge_id=template.reward_badge_id,
            challenge_type=CustomChallengeType.MEDICATION,
            challenge_name="목표 0건 회귀",
            idempotency_key="mysql-zero-goal",
            joined_at=joined_at,
            end_at=joined_at + timedelta(hours=1),
        )
        # Prove the persisted state before a first list read: the
        # second episode was already lazily finalized by prior authenticated API
        # access, while the completed and zero-goal candidates remain due/ACTIVE.
        before_worker = {
            row["id"]: row
            for row in await CustomChallengeParticipation.filter(user=owner).values(
                "id",
                "status",
                "end_at",
                "target_count",
                "completed_count",
                "finalized_at",
            )
        }
        assert set(before_worker) == {first_id, second_id, zero_goal.id}
        assert before_worker[first_id]["status"] == ChallengeParticipationStatus.ACTIVE
        assert before_worker[first_id]["end_at"] <= real_now
        assert before_worker[first_id]["finalized_at"] is None
        # Snapshot counts are deliberately still zero until finalization; the
        # nine scheduled goals were already proven via occurrence rows above.
        assert (before_worker[first_id]["target_count"], before_worker[first_id]["completed_count"]) == (0, 0)
        assert before_worker[second_id]["status"] == ChallengeParticipationStatus.EXPIRED
        assert before_worker[second_id]["end_at"] <= real_now
        assert before_worker[second_id]["finalized_at"] is not None
        assert (before_worker[second_id]["target_count"], before_worker[second_id]["completed_count"]) == (9, 0)
        assert before_worker[zero_goal.id]["status"] == ChallengeParticipationStatus.ACTIVE
        assert before_worker[zero_goal.id]["end_at"] <= real_now
        assert before_worker[zero_goal.id]["finalized_at"] is None
        assert (before_worker[zero_goal.id]["target_count"], before_worker[zero_goal.id]["completed_count"]) == (0, 0)
        first_list = await client.get("/api/v1/user/custom-challenge-participations", headers=owner_headers)
        second_list = await client.get("/api/v1/user/custom-challenge-participations", headers=owner_headers)
        assert first_list.status_code == second_list.status_code == 200
        assert first_list.json() == second_list.json()
        await zero_goal.refresh_from_db()
        assert zero_goal.status is ChallengeParticipationStatus.EXPIRED
        assert await CustomChallengeBadgeAward.filter(user=owner).count() == 0

        completed = await client.get(f"/api/v1/user/custom-challenge-participations/{first_id}", headers=owner_headers)
        expired = await client.get(f"/api/v1/user/custom-challenge-participations/{second_id}", headers=owner_headers)
        zero = await client.get(f"/api/v1/user/custom-challenge-participations/{zero_goal.id}", headers=owner_headers)
        assert (completed.json()["status"], completed.json()["targetCount"], completed.json()["completedCount"]) == (
            ChallengeParticipationStatus.COMPLETED.value,
            9,
            9,
        )
        assert (expired.json()["status"], expired.json()["targetCount"], expired.json()["completedCount"]) == (
            ChallengeParticipationStatus.EXPIRED.value,
            9,
            0,
        )
        assert (zero.json()["status"], zero.json()["targetCount"], zero.json()["completedCount"]) == (
            ChallengeParticipationStatus.EXPIRED.value,
            0,
            0,
        )

        unclaimed_badges = await client.get("/api/v1/user/custom-challenges/badges", headers=owner_headers)
        assert unclaimed_badges.json() == {"items": [], "totalCount": 0}
        assert await CustomChallengeBadgeAward.filter(user=owner).count() == 0
        claimed = await _claim(client, owner_headers, first_id)
        assert claimed["newlyAwarded"] is True
        assert claimed["award"]["participationId"] == first_id
        assert claimed["participation"] == completed.json()
        replay_claim = await _claim(client, owner_headers, first_id)
        assert replay_claim["newlyAwarded"] is False
        assert replay_claim["award"] == claimed["award"]
        for ineligible_id in (second_id, zero_goal.id):
            ineligible = await _claim(client, owner_headers, ineligible_id)
            assert ineligible["award"] is None
            assert ineligible["newlyAwarded"] is False

        badges_before = await client.get("/api/v1/user/custom-challenges/badges", headers=owner_headers)
        other_badges = await client.get("/api/v1/user/custom-challenges/badges", headers=other_headers)
        assert badges_before.status_code == other_badges.status_code == 200
        assert badges_before.json()["totalCount"] == 1
        assert badges_before.json()["items"][0]["participationId"] == first_id
        assert other_badges.json() == {"items": [], "totalCount": 0}
        assert await CustomChallengeBadgeAward.filter(user=owner).count() == 1

        undone = await client.post(
            "/api/v1/medications/doses",
            headers=owner_headers,
            json={
                "date": first_occurrences[0]["scheduledDate"],
                "slot": first_occurrences[0]["slot"].lower(),
                "taken": False,
                "recordId": first_episode.id,
            },
        )
        assert undone.status_code == 200, undone.text
        frozen = await client.get(f"/api/v1/user/custom-challenge-participations/{first_id}", headers=owner_headers)
        badges_after = await client.get("/api/v1/user/custom-challenges/badges", headers=owner_headers)
        assert await MedicationDose.filter(user=owner, care_episode=first_episode).count() == 8
        assert frozen.json() == completed.json()
        assert badges_after.json() == badges_before.json()


async def test_supplement_api_uses_exactly_seven_days_and_freezes_completion_after_undo() -> None:
    """Catches a non-seven-day plan, duplicate award, and recomputation after finalization."""

    real_now = datetime.now(config.TIMEZONE)
    joined_at = (real_now - timedelta(days=8)).replace(hour=7, minute=0, second=0, microsecond=0)
    mutation_at = (real_now - timedelta(days=2)).replace(hour=20, minute=0, second=0, microsecond=0)
    user = await _create_user("mysql315-supplement@example.com")
    registration = await UserSupplementNutrient.create(
        user=user,
        custom_name="7일 비타민",
        dose_amount=Decimal("1"),
        dose_unit="정",
        start_date=joined_at.date(),
        status=SupplementStatus.ACTIVE,
    )
    await UserSupplementNutrientSlot.create(
        user_suppl_nutrient=registration,
        slot=MealSlot.MORNING,
    )
    template = await _template(CustomChallengeType.SUPPLEMENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _auth_headers(client, user.email)
        with _controlled_api_clock(joined_at, custom_challenge_module):
            recommendation = await _recommendation(client, headers, CustomChallengeType.SUPPLEMENT)
            assert [target["id"] for target in recommendation["targets"]] == [registration.id]
            payload = {"targetIds": [registration.id], "idempotencyKey": "mysql-seven-day-supplement"}
            joined = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=headers,
                json=payload,
            )
            replayed = await client.post(
                f"/api/v1/user/custom-challenge-recommendations/{template.id}/participations",
                headers=headers,
                json=payload,
            )
        assert joined.status_code == replayed.status_code == 201
        assert replayed.json() == joined.json()
        participation_id = joined.json()["id"]
        occurrences = joined.json()["occurrences"]
        assert len(occurrences) == joined.json()["targetCount"] == 7
        assert len({item["scheduledDate"] for item in occurrences}) == 7
        assert await CustomChallengeParticipation.filter(user=user).count() == 1

        with _controlled_api_clock(mutation_at, supplement_dose_module):
            for occurrence in occurrences:
                saved = await client.put(
                    "/api/v1/med/supplement-doses",
                    headers=headers,
                    json={
                        "supplementId": registration.id,
                        "date": occurrence["scheduledDate"],
                        "slot": occurrence["slot"].lower(),
                        "taken": True,
                    },
                )
                assert saved.status_code == 200, saved.text
        assert await SupplementDose.filter(registration=registration).count() == 7

        # A first post-end read and undo share the same user lock; neither
        # awards a badge until explicit detail claim.
        first_read, undone = await asyncio.gather(
            client.get("/api/v1/user/custom-challenge-participations", headers=headers),
            client.put(
                "/api/v1/med/supplement-doses",
                headers=headers,
                json={
                    "supplementId": registration.id,
                    "date": occurrences[0]["scheduledDate"],
                    "slot": occurrences[0]["slot"].lower(),
                    "taken": False,
                },
            ),
        )
        assert undone.status_code == 200, undone.text
        assert first_read.status_code == 200, first_read.text

        completed = await client.get(
            f"/api/v1/user/custom-challenge-participations/{participation_id}", headers=headers
        )
        unclaimed_badges = await client.get("/api/v1/user/custom-challenges/badges", headers=headers)
        assert unclaimed_badges.json() == {"items": [], "totalCount": 0}
        assert await CustomChallengeBadgeAward.filter(participation_id=participation_id).count() == 0
        claimed = await _claim(client, headers, participation_id)
        assert claimed["newlyAwarded"] is True
        assert claimed["participation"] == completed.json()
        assert claimed["award"]["participationId"] == participation_id
        badges_before = await client.get("/api/v1/user/custom-challenges/badges", headers=headers)
        assert (completed.json()["status"], completed.json()["targetCount"], completed.json()["completedCount"]) == (
            ChallengeParticipationStatus.COMPLETED.value,
            7,
            7,
        )
        assert Decimal(str(completed.json()["progressRate"])) == Decimal("100.00")
        assert badges_before.json()["totalCount"] == 1
        assert await CustomChallengeBadgeAward.filter(participation_id=participation_id).count() == 1
        frozen = await client.get(f"/api/v1/user/custom-challenge-participations/{participation_id}", headers=headers)
        badges_after = await client.get("/api/v1/user/custom-challenges/badges", headers=headers)
        assert await SupplementDose.filter(registration=registration).count() == 6
        assert frozen.json() == completed.json()
        assert badges_after.json() == badges_before.json()
