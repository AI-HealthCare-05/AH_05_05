from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationDose, MedicationSlot
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


async def create_overview_episode(
    user: User,
    *,
    start_date: date,
    days: int = 1,
    source_ocr_job_id: int,
    episode_status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE,
) -> CareEpisode:
    episode = await create_episode(
        user,
        start_date=start_date,
        medication_days=days,
        source_ocr_job_id=source_ocr_job_id,
        episode_status=episode_status,
    )
    await Medication.create(
        care_episode=episode,
        name=f"{start_date.isoformat()} 처방약",
        times_per_day=1,
        days=days,
    )
    return episode


class TestMedicationOverviewAPI(TestCase):
    async def test_routes_require_authentication(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            overview = await client.get(OVERVIEW_URL)
            history = await client.get(
                DOSES_URL,
                params={"from": "2026-08-01", "to": "2026-08-07"},
            )
            save = await client.post(
                DOSES_URL,
                json={"date": "2026-08-01", "slot": "morning", "taken": True},
            )
            cancel = await client.delete(f"{OVERVIEW_URL}/1")

        assert overview.status_code == status.HTTP_401_UNAUTHORIZED
        assert history.status_code == status.HTTP_401_UNAUTHORIZED
        assert save.status_code == status.HTTP_401_UNAUTHORIZED
        assert cancel.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_new_user_receives_empty_array_instead_of_not_found(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "overview-empty@example.com", "01023000001")
            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_overview_orders_by_start_date_then_id_descending(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-registration-order@example.com"
            headers = await authentication_headers(client, email, "01023000014")
            user = await User.get(email=email)
            newest_start = await create_overview_episode(
                user,
                start_date=today,
                source_ocr_job_id=201,
            )
            older_start_first = await create_overview_episode(
                user,
                start_date=today - timedelta(days=10),
                source_ocr_job_id=202,
            )
            older_start_second = await create_overview_episode(
                user,
                start_date=today - timedelta(days=10),
                source_ocr_job_id=203,
            )

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert [overview["recordId"] for overview in response.json()] == [
            newest_start.id,
            older_start_second.id,
            older_start_first.id,
        ]

    async def test_overview_defaults_to_recent_six_calendar_months(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        boundary = today - relativedelta(months=6)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-default-range@example.com"
            headers = await authentication_headers(client, email, "01023000015")
            user = await User.get(email=email)
            included_boundary = await create_overview_episode(
                user,
                start_date=boundary,
                source_ocr_job_id=204,
            )
            included_today = await create_overview_episode(
                user,
                start_date=today,
                source_ocr_job_id=205,
            )
            await create_overview_episode(
                user,
                start_date=boundary - timedelta(days=1),
                source_ocr_job_id=206,
            )
            await create_overview_episode(
                user,
                start_date=today + timedelta(days=1),
                source_ocr_job_id=207,
            )

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert [item["recordId"] for item in response.json()] == [included_today.id, included_boundary.id]

    async def test_overview_uses_explicit_range_and_excludes_cancelled_episode(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        from_date = today - timedelta(days=20)
        to_date = today - timedelta(days=10)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-explicit-range@example.com"
            headers = await authentication_headers(client, email, "01023000016")
            user = await User.get(email=email)
            included_from = await create_overview_episode(
                user,
                start_date=from_date,
                source_ocr_job_id=208,
            )
            included_to = await create_overview_episode(
                user,
                start_date=to_date,
                source_ocr_job_id=209,
            )
            await create_overview_episode(
                user,
                start_date=from_date - timedelta(days=1),
                source_ocr_job_id=210,
            )
            await create_overview_episode(
                user,
                start_date=to_date + timedelta(days=1),
                source_ocr_job_id=211,
            )
            await create_overview_episode(
                user,
                start_date=to_date,
                source_ocr_job_id=212,
                episode_status=CareEpisodeStatus.CANCELLED,
            )

            response = await client.get(
                OVERVIEW_URL,
                params={"from": from_date.isoformat(), "to": to_date.isoformat()},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert [item["recordId"] for item in response.json()] == [included_to.id, included_from.id]

    async def test_overview_resolves_single_sided_ranges(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        from_date = today - relativedelta(months=12)
        from_range_end = from_date + relativedelta(months=6)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-single-sided-range@example.com"
            headers = await authentication_headers(client, email, "01023000017")
            user = await User.get(email=email)
            from_boundary = await create_overview_episode(
                user,
                start_date=from_date,
                source_ocr_job_id=213,
            )
            from_end_boundary = await create_overview_episode(
                user,
                start_date=from_range_end,
                source_ocr_job_id=214,
            )
            today_boundary = await create_overview_episode(
                user,
                start_date=today,
                source_ocr_job_id=215,
            )

            from_only = await client.get(
                OVERVIEW_URL,
                params={"from": from_date.isoformat()},
                headers=headers,
            )
            to_only = await client.get(
                OVERVIEW_URL,
                params={"to": today.isoformat()},
                headers=headers,
            )

        assert from_only.status_code == status.HTTP_200_OK
        assert [item["recordId"] for item in from_only.json()] == [from_end_boundary.id, from_boundary.id]
        assert to_only.status_code == status.HTTP_200_OK
        assert [item["recordId"] for item in to_only.json()] == [today_boundary.id]

    async def test_overview_allows_last_two_years_and_rejects_older_or_future_dates(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "overview-invalid-range@example.com", "01023000018")
            reversed_range = await client.get(
                OVERVIEW_URL,
                params={"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()},
                headers=headers,
            )
            exact_two_years = await client.get(
                OVERVIEW_URL,
                params={
                    "from": (today - relativedelta(years=2)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            too_old = await client.get(
                OVERVIEW_URL,
                params={
                    "from": (today - relativedelta(years=2, days=1)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            future = await client.get(
                OVERVIEW_URL,
                params={"from": today.isoformat(), "to": (today + timedelta(days=1)).isoformat()},
                headers=headers,
            )

        assert reversed_range.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert exact_two_years.status_code == status.HTTP_200_OK
        assert too_old.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert future.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_overview_is_finished_only_after_end_date(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "overview-finished@example.com"
            headers = await authentication_headers(client, email, "01023000019")
            user = await User.get(email=email)
            finished = await create_overview_episode(
                user,
                start_date=today - timedelta(days=1),
                source_ocr_job_id=216,
            )
            ending_today = await create_overview_episode(
                user,
                start_date=today,
                source_ocr_job_id=217,
            )
            ending_tomorrow = await create_overview_episode(
                user,
                start_date=today,
                days=2,
                source_ocr_job_id=218,
            )

            response = await client.get(OVERVIEW_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        finished_by_id = {item["recordId"]: item["isFinished"] for item in response.json()}
        assert finished_by_id == {
            finished.id: True,
            ending_today.id: False,
            ending_tomorrow.id: False,
        }

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
                strength="200mg",
                times_per_day=2,
                days=7,
            )
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.EVENING)
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.MORNING)

            until_complete = await Medication.create(
                care_episode=first,
                name="리바록사반",
                strength="10mg",
                times_per_day=1,
                days=None,
            )
            await MedicationSlot.create(medication=until_complete, slot=MealSlot.EVENING)

            as_needed = await Medication.create(
                care_episode=first,
                name="아세트아미노펜",
                strength="650mg",
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
                strength="500mg",
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
        assert sorted(response.json(), key=lambda overview: overview["recordId"]) == [
            {
                "recordId": first.id,
                "documentImageUrl": "/api/v1/ocr/jobs/12/image",
                "start": {"date": first_start.isoformat(), "slot": "morning"},
                "endDate": (first_start + timedelta(days=9)).isoformat(),
                "daysRemaining": 8,
                "isFinished": False,
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
                "isFinished": False,
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
    async def test_save_without_record_id_and_delete_are_idempotent(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        target_date = today - timedelta(days=1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-idempotent@example.com"
            headers = await authentication_headers(client, email, "01023000003")
            user = await User.get(email=email)
            payload = {
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
            assert (
                await MedicationDose.filter(
                    user=user,
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
        assert await MedicationDose.filter(user=user).count() == 0

    async def test_dose_is_shared_across_episodes(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-shared@example.com"
            headers = await authentication_headers(client, email, "01023000013")
            user = await User.get(email=email)
            await create_episode(user, start_date=today - timedelta(days=2))
            await create_episode(user, start_date=today - timedelta(days=1))

            response = await client.post(
                DOSES_URL,
                json={
                    "date": today.isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert await MedicationDose.filter(user=user, dose_date=today, slot=MealSlot.MORNING).count() == 1

    async def test_save_accepts_366_day_window_and_rejects_dates_outside_it(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "dose-validation@example.com", "01023000004")

            earliest = await client.post(
                DOSES_URL,
                json={
                    "date": (today - timedelta(days=365)).isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )
            too_old = await client.post(
                DOSES_URL,
                json={
                    "date": (today - timedelta(days=366)).isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )
            future = await client.post(
                DOSES_URL,
                json={
                    "date": (today + timedelta(days=1)).isoformat(),
                    "slot": "morning",
                    "taken": True,
                },
                headers=headers,
            )
            invalid_slot = await client.post(
                DOSES_URL,
                json={
                    "date": today.isoformat(),
                    "slot": "breakfast",
                    "taken": True,
                },
                headers=headers,
            )

        assert earliest.status_code == status.HTTP_200_OK
        assert too_old.status_code == status.HTTP_400_BAD_REQUEST
        assert too_old.json()["code"] == "INVALID_DOSE_DATE"
        assert future.status_code == status.HTTP_400_BAD_REQUEST
        assert future.json()["code"] == "INVALID_DOSE_DATE"
        assert invalid_slot.status_code == status.HTTP_400_BAD_REQUEST
        assert invalid_slot.json()["code"] == "INVALID_SLOT"

    async def test_history_returns_all_user_records_in_range_without_record_id(self) -> None:
        start_date = datetime.now(config.TIMEZONE).date() - timedelta(days=5)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "dose-history@example.com"
            headers = await authentication_headers(client, email, "01023000007")
            user = await User.get(email=email)
            other_headers = await authentication_headers(client, "dose-history-other@example.com", "01023000014")
            other_user = await User.get(email="dose-history-other@example.com")

            await MedicationDose.create(user=user, dose_date=start_date, slot=MealSlot.EVENING)
            await MedicationDose.create(user=user, dose_date=start_date, slot=MealSlot.MORNING)
            await MedicationDose.create(
                user=user,
                dose_date=start_date + timedelta(days=4),
                slot=MealSlot.BEDTIME,
            )
            await MedicationDose.create(user=other_user, dose_date=start_date, slot=MealSlot.LUNCH)

            response = await client.get(
                DOSES_URL,
                params={
                    "from": start_date.isoformat(),
                    "to": (start_date + timedelta(days=2)).isoformat(),
                },
                headers=headers,
            )
            other_response = await client.get(
                DOSES_URL,
                params={"from": start_date.isoformat(), "to": start_date.isoformat()},
                headers=other_headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == [
            {"date": start_date.isoformat(), "slot": "morning", "taken": True},
            {"date": start_date.isoformat(), "slot": "evening", "taken": True},
        ]
        assert other_response.status_code == status.HTTP_200_OK
        assert other_response.json() == [{"date": start_date.isoformat(), "slot": "lunch", "taken": True}]

    async def test_history_accepts_366_days_and_rejects_367_days(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "dose-history-range@example.com", "01023000008")

            valid = await client.get(
                DOSES_URL,
                params={
                    "from": (today - timedelta(days=365)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            too_wide = await client.get(
                DOSES_URL,
                params={
                    "from": (today - timedelta(days=366)).isoformat(),
                    "to": today.isoformat(),
                },
                headers=headers,
            )
            reversed_range = await client.get(
                DOSES_URL,
                params={
                    "from": today.isoformat(),
                    "to": (today - timedelta(days=1)).isoformat(),
                },
                headers=headers,
            )

        assert valid.status_code == status.HTTP_200_OK
        assert valid.json() == []
        assert too_wide.status_code == status.HTTP_400_BAD_REQUEST
        assert too_wide.json()["code"] == "INVALID_DOSE_DATE_RANGE"
        assert reversed_range.status_code == status.HTTP_400_BAD_REQUEST
        assert reversed_range.json()["code"] == "INVALID_DOSE_DATE_RANGE"


class TestMedicationCancellationAPI(TestCase):
    async def test_cancel_is_idempotent_and_hides_episode_from_overview(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "cancel-idempotent@example.com"
            headers = await authentication_headers(client, email, "01023000015")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today, source_ocr_job_id=201)
            await Medication.create(care_episode=episode, name="취소할 약", times_per_day=1, days=7)

            first = await client.delete(f"{OVERVIEW_URL}/{episode.id}", headers=headers)
            second = await client.delete(f"{OVERVIEW_URL}/{episode.id}", headers=headers)
            overview = await client.get(OVERVIEW_URL, headers=headers)

        await episode.refresh_from_db()
        assert first.status_code == status.HTTP_204_NO_CONTENT
        assert second.status_code == status.HTTP_204_NO_CONTENT
        assert episode.status == CareEpisodeStatus.CANCELLED
        assert overview.status_code == status.HTTP_200_OK
        assert overview.json() == []

    async def test_dose_survives_episode_cancel(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "cancel-dose@example.com"
            headers = await authentication_headers(client, email, "01023000016")
            user = await User.get(email=email)
            episode = await create_episode(user, start_date=today, source_ocr_job_id=202)
            await Medication.create(care_episode=episode, name="기록을 남길 약", times_per_day=1, days=7)

            saved = await client.post(
                DOSES_URL,
                json={"date": today.isoformat(), "slot": "morning", "taken": True},
                headers=headers,
            )
            cancelled = await client.delete(f"{OVERVIEW_URL}/{episode.id}", headers=headers)

        assert saved.status_code == status.HTTP_200_OK
        assert cancelled.status_code == status.HTTP_204_NO_CONTENT
        assert await MedicationDose.filter(user=user, dose_date=today, slot=MealSlot.MORNING).count() == 1

    async def test_cancel_other_users_record_returns_403_and_missing_returns_404(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_email = "cancel-owner@example.com"
            await authentication_headers(client, owner_email, "01023000017")
            other_headers = await authentication_headers(client, "cancel-other@example.com", "01023000018")
            owner = await User.get(email=owner_email)
            episode = await create_episode(owner, start_date=today)

            forbidden = await client.delete(f"{OVERVIEW_URL}/{episode.id}", headers=other_headers)
            missing = await client.delete(f"{OVERVIEW_URL}/999999999", headers=other_headers)

        assert forbidden.status_code == status.HTTP_403_FORBIDDEN
        assert forbidden.json()["code"] == "MEDICATION_RECORD_FORBIDDEN"
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        assert missing.json()["code"] == "MEDICATION_RECORD_NOT_FOUND"
