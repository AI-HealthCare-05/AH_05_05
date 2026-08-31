from datetime import date, datetime, time, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User, UserSettings
from app.tests.med_apis.helpers import authentication_headers

OVERVIEW_URL = "/api/v1/medications"
DOSES_URL = "/api/v1/medications/doses"


async def create_episode(
    user: User,
    *,
    start_date: date,
    start_slot: MealSlot = MealSlot.MORNING,
    medication_days: int | None = 7,
    source_ocr_job_id: int | None = None,
    episode_status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE,
) -> CareEpisode:
    return await CareEpisode.create(
        user=user,
        title=f"{start_date.isoformat()} 조제약 복약안내",
        status=episode_status,
        medication_start_date=start_date,
        medication_start_slot=start_slot,
        medication_days=medication_days,
        source_ocr_job_id=source_ocr_job_id,
    )


class TestMedicationOverviewAPI(TestCase):
    async def test_routes_require_authentication(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            overview = await client.get(OVERVIEW_URL)
            history = await client.get(
                DOSES_URL,
                params={"recordId": 1, "from": "2026-08-01", "to": "2026-08-07"},
            )
            save = await client.post(
                DOSES_URL,
                json={"recordId": 1, "date": "2026-08-01", "slot": "morning", "taken": True},
            )

        assert overview.status_code == status.HTTP_401_UNAUTHORIZED
        assert history.status_code == status.HTTP_401_UNAUTHORIZED
        assert save.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_new_user_receives_empty_array_instead_of_not_found(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "overview-empty@example.com", "01023000001")
            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_overview_includes_episode_without_start_slot(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-no-slot@example.com"
            headers = await authentication_headers(client, email, "01023000009")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today, source_ocr_job_id=101)
            episode.medication_start_slot = None
            await episode.save(update_fields=["medication_start_slot"])
            medication = await Medication.create(
                care_episode=episode,
                name="세레콕시브",
                times_per_day=2,
                days=7,
            )
            await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()[0]["recordId"] == episode.id
        assert response.json()[0]["start"]["slot"] == "morning"

    async def test_end_date_excludes_as_needed_medication(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-prn-end@example.com"
            headers = await authentication_headers(client, email, "01023000010")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today, source_ocr_job_id=102)
            scheduled = await Medication.create(
                care_episode=episode,
                name="세레콕시브",
                times_per_day=2,
                days=7,
            )
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.MORNING)
            await Medication.create(
                care_episode=episode,
                name="아세트아미노펜",
                times_per_day=None,
                days=30,
            )

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()[0]["endDate"] == (today + timedelta(days=6)).isoformat()

    async def test_overview_when_all_medication_days_unknown(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-unknown-days@example.com"
            headers = await authentication_headers(client, email, "01023000011")
            user = await User.get(email=email)
            episode = await create_episode(
                user,
                start_date=today,
                medication_days=None,
                source_ocr_job_id=103,
            )
            first = await Medication.create(
                care_episode=episode,
                name="일수 미상 약 1",
                times_per_day=1,
                days=None,
            )
            second = await Medication.create(
                care_episode=episode,
                name="일수 미상 약 2",
                times_per_day=1,
                days=None,
            )
            await MedicationSlot.create(medication=first, slot=MealSlot.MORNING)
            await MedicationSlot.create(medication=second, slot=MealSlot.EVENING)

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        overview = response.json()[0]
        assert overview["endDate"] == today.isoformat()
        assert overview["daysRemaining"] == 1
        assert all(item["days"] == 1 for item in overview["medications"])
        assert all(item["daysRemaining"] == 1 for item in overview["medications"])
        assert all(item["untilComplete"] is True for item in overview["medications"])

    async def test_overview_returns_other_episodes_when_one_has_unknown_days(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-mixed-days@example.com"
            headers = await authentication_headers(client, email, "01023000012")
            user = await User.get(email=email)
            unknown = await create_episode(
                user,
                start_date=today,
                medication_days=None,
                source_ocr_job_id=104,
            )
            await Medication.create(
                care_episode=unknown,
                name="일수 미상 약",
                times_per_day=1,
                days=None,
            )
            normal = await create_episode(
                user,
                start_date=today,
                medication_days=7,
                source_ocr_job_id=105,
            )
            await Medication.create(
                care_episode=normal,
                name="7일 약",
                times_per_day=1,
                days=7,
            )

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert {overview["recordId"] for overview in response.json()} == {unknown.id, normal.id}

    async def test_returns_all_active_episodes_with_frontend_contract_and_hand_checked_dates(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-contract@example.com"
            headers = await authentication_headers(client, email, "01023000002")
            user = await User.get(email=email)
            settings = await UserSettings.get(user=user)
            settings.morning_medication_time = time(7, 30)
            settings.lunch_medication_time = time(12, 0)
            settings.evening_medication_time = time(18, 30)
            settings.bedtime_medication_time = time(22, 0)
            await settings.save()

            first_start = today - timedelta(days=2)
            first = await create_episode(
                user,
                start_date=first_start,
                medication_days=10,
                source_ocr_job_id=12,
            )
            scheduled = await Medication.create(
                care_episode=first,
                name="셀레콕시브",
                dose="200mg",
                times_per_day=2,
                days=7,
            )
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.EVENING)
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.MORNING)

            until_complete = await Medication.create(
                care_episode=first,
                name="리바록사반",
                dose="10mg",
                times_per_day=1,
                days=None,
            )
            await MedicationSlot.create(medication=until_complete, slot=MealSlot.EVENING)

            as_needed = await Medication.create(
                care_episode=first,
                name="아세트아미노펜",
                dose="650mg",
                times_per_day=None,
                days=7,
            )
            # 과거 잘못된 설정이 남아 있어도 필요 시 복용약은 슬롯 응답 대상이 아니다.
            await MedicationSlot.create(medication=as_needed, slot=MealSlot.LUNCH)

            second_start = today - timedelta(days=1)
            second = await create_episode(
                user,
                start_date=second_start,
                start_slot=MealSlot.LUNCH,
                medication_days=5,
                source_ocr_job_id=24,
            )
            second_medication = await Medication.create(
                care_episode=second,
                name="아목시실린",
                dose="500mg",
                times_per_day=3,
                days=5,
            )
            for slot in (MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING):
                await MedicationSlot.create(medication=second_medication, slot=slot)

            cancelled = await create_episode(
                user,
                start_date=today,
                episode_status=CareEpisodeStatus.CANCELLED,
            )
            await Medication.create(care_episode=cancelled, name="제외할 약", times_per_day=1, days=30)

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == [
            {
                "recordId": first.id,
                "documentImageUrl": "/api/v1/ocr/jobs/12/image",
                "start": {"date": first_start.isoformat(), "slot": "morning"},
                "endDate": (first_start + timedelta(days=9)).isoformat(),
                "daysRemaining": 8,
                "mealTimes": {
                    "morning": "07:30",
                    "lunch": "12:00",
                    "evening": "18:30",
                    "bedtime": "22:00",
                },
                "medications": [
                    {
                        "medicationId": scheduled.id,
                        "name": "셀레콕시브",
                        "dose": "200mg",
                        "days": 7,
                        "daysRemaining": 5,
                        "slots": ["morning", "evening"],
                        "asNeeded": False,
                    },
                    {
                        "medicationId": until_complete.id,
                        "name": "리바록사반",
                        "dose": "10mg",
                        "days": 10,
                        "daysRemaining": 8,
                        "slots": ["evening"],
                        "asNeeded": False,
                        "untilComplete": True,
                    },
                    {
                        "medicationId": as_needed.id,
                        "name": "아세트아미노펜",
                        "dose": "650mg",
                        "days": 7,
                        "daysRemaining": None,
                        "slots": [],
                        "asNeeded": True,
                    },
                ],
            },
            {
                "recordId": second.id,
                "documentImageUrl": "/api/v1/ocr/jobs/24/image",
                "start": {"date": second_start.isoformat(), "slot": "lunch"},
                "endDate": (second_start + timedelta(days=4)).isoformat(),
                "daysRemaining": 4,
                "mealTimes": {
                    "morning": "07:30",
                    "lunch": "12:00",
                    "evening": "18:30",
                    "bedtime": "22:00",
                },
                "medications": [
                    {
                        "medicationId": second_medication.id,
                        "name": "아목시실린",
                        "dose": "500mg",
                        "days": 5,
                        "daysRemaining": 4,
                        "slots": ["morning", "lunch", "evening"],
                        "asNeeded": False,
                    }
                ],
            },
        ]


class TestMedicationDoseAPI(TestCase):
    async def test_save_and_delete_are_idempotent(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        target_date = today - timedelta(days=1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-idempotent@example.com"
            headers = await authentication_headers(client, email, "01023000003")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today - timedelta(days=2))
            payload = {
                "recordId": episode.id,
                "date": target_date.isoformat(),
                "slot": "morning",
                "taken": True,
            }

            first = await client.post(DOSES_URL, json=payload, headers=headers)
            second = await client.post(DOSES_URL, json=payload, headers=headers)

            assert first.status_code == status.HTTP_200_OK
            assert second.status_code == status.HTTP_200_OK
            assert first.json() == payload
            assert second.json() == payload

            from app.models.medications import MedicationDose

            assert (
                await MedicationDose.filter(
                    user=user,
                    care_episode=episode,
                    dose_date=target_date,
                    slot=MealSlot.MORNING,
                ).count()
                == 1
            )

            payload["taken"] = False
            deleted = await client.post(DOSES_URL, json=payload, headers=headers)
            deleted_again = await client.post(DOSES_URL, json=payload, headers=headers)

        assert deleted.status_code == status.HTTP_200_OK
        assert deleted_again.status_code == status.HTTP_200_OK
        assert deleted.json() == payload
        assert deleted_again.json() == payload
        assert await MedicationDose.filter(care_episode=episode).count() == 0

    async def test_save_rejects_out_of_range_date_and_invalid_slot(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        start_date = today - timedelta(days=2)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-validation@example.com"
            headers = await authentication_headers(client, email, "01023000004")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=start_date)

            before_start = await client.post(
                DOSES_URL,
                json={
                    "recordId": episode.id,
                    "date": (start_date - timedelta(days=1)).isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )
            future = await client.post(
                DOSES_URL,
                json={
                    "recordId": episode.id,
                    "date": (today + timedelta(days=1)).isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )
            invalid_slot = await client.post(
                DOSES_URL,
                json={
                    "recordId": episode.id,
                    "date": today.isoformat(),
                    "slot": "breakfast",
                    "taken": True,
                },
                headers=headers,
            )

        assert before_start.status_code == status.HTTP_400_BAD_REQUEST
        assert before_start.json()["code"] == "invalid_dose_date"
        assert future.status_code == status.HTTP_400_BAD_REQUEST
        assert future.json()["code"] == "invalid_dose_date"
        assert invalid_slot.status_code == status.HTTP_400_BAD_REQUEST
        assert invalid_slot.json()["code"] == "invalid_slot"

    async def test_record_access_distinguishes_missing_and_other_users_record(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_email = "dose-owner@example.com"
            await authentication_headers(client, owner_email, "01023000005")
            other_headers = await authentication_headers(client, "dose-other@example.com", "01023000006")
            owner = await User.get(email=owner_email)
            episode = await create_episode(owner, start_date=today)

            forbidden = await client.post(
                DOSES_URL,
                json={
                    "recordId": episode.id,
                    "date": today.isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=other_headers,
            )
            missing = await client.post(
                DOSES_URL,
                json={
                    "recordId": 999999999,
                    "date": today.isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=other_headers,
            )
            forbidden_history = await client.get(
                DOSES_URL,
                params={"recordId": episode.id, "from": today.isoformat(), "to": today.isoformat()},
                headers=other_headers,
            )
            missing_history = await client.get(
                DOSES_URL,
                params={"recordId": 999999999, "from": today.isoformat(), "to": today.isoformat()},
                headers=other_headers,
            )

        assert forbidden.status_code == status.HTTP_403_FORBIDDEN
        assert forbidden.json()["code"] == "forbidden"
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        assert missing.json()["code"] == "record_not_found"
        assert forbidden_history.status_code == status.HTTP_403_FORBIDDEN
        assert forbidden_history.json()["code"] == "forbidden"
        assert missing_history.status_code == status.HTTP_404_NOT_FOUND
        assert missing_history.json()["code"] == "record_not_found"

    async def test_history_returns_only_existing_records_for_requested_episode_and_range(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        start_date = today - timedelta(days=5)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-history@example.com"
            headers = await authentication_headers(client, email, "01023000007")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=start_date)
            other_episode = await create_episode(user, start_date=start_date)

            from app.models.medications import MedicationDose

            await MedicationDose.create(
                user=user,
                care_episode=episode,
                dose_date=start_date,
                slot=MealSlot.EVENING,
            )
            await MedicationDose.create(
                user=user,
                care_episode=episode,
                dose_date=start_date,
                slot=MealSlot.MORNING,
            )
            await MedicationDose.create(
                user=user,
                care_episode=episode,
                dose_date=start_date + timedelta(days=4),
                slot=MealSlot.BEDTIME,
            )
            await MedicationDose.create(
                user=user,
                care_episode=other_episode,
                dose_date=start_date,
                slot=MealSlot.LUNCH,
            )

            response = await client.get(
                DOSES_URL,
                params={
                    "recordId": episode.id,
                    "from": start_date.isoformat(),
                    "to": (start_date + timedelta(days=2)).isoformat(),
                },
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == [
            {"recordId": episode.id, "date": start_date.isoformat(), "slot": "morning", "taken": True},
            {"recordId": episode.id, "date": start_date.isoformat(), "slot": "evening", "taken": True},
        ]

    async def test_empty_history_is_normal_and_range_is_bounded(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-history-range@example.com"
            headers = await authentication_headers(client, email, "01023000008")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today - timedelta(days=100))

            empty = await client.get(
                DOSES_URL,
                params={
                    "recordId": episode.id,
                    "from": (today - timedelta(days=30)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            too_wide = await client.get(
                DOSES_URL,
                params={
                    "recordId": episode.id,
                    "from": (today - timedelta(days=93)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            reversed_range = await client.get(
                DOSES_URL,
                params={
                    "recordId": episode.id,
                    "from": today.isoformat(),
                    "to": (today - timedelta(days=1)).isoformat(),
                },
                headers=headers,
            )

        assert empty.status_code == status.HTTP_200_OK
        assert empty.json() == []
        assert too_wide.status_code == status.HTTP_400_BAD_REQUEST
        assert too_wide.json()["code"] == "invalid_dose_date_range"
        assert reversed_range.status_code == status.HTTP_400_BAD_REQUEST
        assert reversed_range.json()["code"] == "invalid_dose_date_range"
