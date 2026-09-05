from datetime import date, datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.care import CareEpisode
from app.models.medications import Medication, MedicationNote
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers

ALIAS_URL = "/api/v1/med/episodes"
MEDICATIONS_URL = "/api/v1/medications"
NOTES_URL = "/api/v1/med/notes"


async def create_episode(user: User, *, title: str, alias: str | None = None) -> CareEpisode:
    return await CareEpisode.create(
        user=user,
        title=title,
        alias=alias,
        source_ocr_job_id=1,
        medication_start_date=date(2026, 9, 3),
        medication_days=7,
    )


class TestMedicationAliasAPI(TestCase):
    async def test_alias_is_trimmed_persisted_and_returned_in_overview(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "alias-owner@example.com", "01025000001")
            user = await User.get(email="alias-owner@example.com")
            episode = await create_episode(user, title="2026-09-03 조제약 복약안내")
            medication = await Medication.create(
                care_episode=episode,
                name="테스트 약",
                times_per_day=1,
                days=7,
            )

            updated = await client.patch(
                f"{ALIAS_URL}/{episode.id}/alias",
                json={"alias": "  감기약  "},
                headers=headers,
            )
            overview = await client.get(MEDICATIONS_URL, headers=headers)

        assert updated.status_code == status.HTTP_200_OK
        assert updated.json() == {"alias": "감기약"}
        assert overview.status_code == status.HTTP_200_OK
        assert overview.json()[0]["recordId"] == episode.id
        assert overview.json()[0]["alias"] == "감기약"
        assert medication.id in [item["medicationId"] for item in overview.json()[0]["medications"]]
        await episode.refresh_from_db()
        assert episode.title == "2026-09-03 조제약 복약안내"

    async def test_alias_blank_value_clears_alias_and_other_users_are_hidden(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_headers = await authentication_headers(client, "alias-owner-2@example.com", "01025000002")
            other_headers = await authentication_headers(client, "alias-other@example.com", "01025000003")
            owner = await User.get(email="alias-owner-2@example.com")
            episode = await create_episode(owner, title="2026-09-03 조제약 복약안내", alias="기존 별칭")

            cleared = await client.patch(
                f"{ALIAS_URL}/{episode.id}/alias",
                json={"alias": "   "},
                headers=owner_headers,
            )
            forbidden = await client.patch(
                f"{ALIAS_URL}/{episode.id}/alias",
                json={"alias": "남의 처방"},
                headers=other_headers,
            )
            missing = await client.patch(
                f"{ALIAS_URL}/999999999/alias",
                json={"alias": "없음"},
                headers=other_headers,
            )

        await episode.refresh_from_db()
        assert cleared.status_code == status.HTTP_200_OK
        assert cleared.json() == {"alias": None}
        assert episode.alias is None
        assert forbidden.status_code == status.HTTP_404_NOT_FOUND
        assert forbidden.json()["code"] == "MEDICATION_RECORD_NOT_FOUND"
        assert missing.status_code == status.HTTP_404_NOT_FOUND


class TestMedicationNotesAPI(TestCase):
    async def test_note_crud_uses_dosed_at_order_and_allows_an_optional_medication(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "note-owner@example.com", "01025000004")
            user = await User.get(email="note-owner@example.com")
            episode = await create_episode(user, title="2026-09-03 조제약 복약안내")
            medication = await Medication.create(
                care_episode=episode,
                name="메모 약",
                times_per_day=1,
                days=7,
            )
            older = datetime(2026, 9, 2, 19, 0)
            newer = datetime(2026, 9, 3, 8, 0)

            first = await client.post(
                NOTES_URL,
                json={
                    "careEpisodeId": episode.id,
                    "medicationId": medication.id,
                    "dosedAt": older.isoformat(),
                    "body": "어제 저녁에는 괜찮았어요.",
                },
                headers=headers,
            )
            second = await client.post(
                NOTES_URL,
                json={
                    "careEpisodeId": episode.id,
                    "dosedAt": newer.isoformat(),
                    "body": "오늘 아침에는 조금 어지러웠어요.",
                },
                headers=headers,
            )
            listed = await client.get(
                NOTES_URL,
                params={"episodeId": episode.id, "limit": 10},
                headers=headers,
            )

            note_id = first.json()["id"]
            updated = await client.patch(
                f"{NOTES_URL}/{note_id}",
                json={"body": "수정한 메모", "dosedAt": newer.isoformat()},
                headers=headers,
            )
            deleted = await client.delete(f"{NOTES_URL}/{note_id}", headers=headers)
            after_delete = await client.get(NOTES_URL, headers=headers)

        assert first.status_code == status.HTTP_201_CREATED
        assert first.json()["careEpisodeId"] == episode.id
        assert first.json()["medicationId"] == medication.id
        assert first.json()["dosedAt"].startswith("2026-09-02T19:00")
        assert second.status_code == status.HTTP_201_CREATED
        assert second.json()["medicationId"] is None
        assert listed.status_code == status.HTTP_200_OK
        assert [item["body"] for item in listed.json()] == [
            "오늘 아침에는 조금 어지러웠어요.",
            "어제 저녁에는 괜찮았어요.",
        ]
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["body"] == "수정한 메모"
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert after_delete.json() == [second.json()]
        assert await MedicationNote.filter(id=note_id).exists() is False

    async def test_note_routes_hide_other_users_and_validate_episode_and_medication_ownership(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_headers = await authentication_headers(client, "note-owner-2@example.com", "01025000005")
            other_headers = await authentication_headers(client, "note-other@example.com", "01025000006")
            owner = await User.get(email="note-owner-2@example.com")
            other = await User.get(email="note-other@example.com")
            episode = await create_episode(owner, title="2026-09-03 조제약 복약안내")
            other_episode = await create_episode(other, title="2026-09-03 다른 처방")
            medication = await Medication.create(
                care_episode=episode,
                name="소유 약",
                times_per_day=1,
                days=7,
            )
            other_medication = await Medication.create(
                care_episode=other_episode,
                name="남의 약",
                times_per_day=1,
                days=7,
            )
            note = await MedicationNote.create(
                user=owner,
                care_episode=episode,
                medication=medication,
                dosed_at=datetime(2026, 9, 3, 8, 0),
                body="소유자 메모",
            )
            payload = {
                "careEpisodeId": episode.id,
                "medicationId": medication.id,
                "dosedAt": datetime(2026, 9, 3, 9, 0).isoformat(),
                "body": "새 메모",
            }

            other_get = await client.get(f"{NOTES_URL}/{note.id}", headers=other_headers)
            other_patch = await client.patch(
                f"{NOTES_URL}/{note.id}",
                json={"body": "훔친 수정"},
                headers=other_headers,
            )
            other_delete = await client.delete(f"{NOTES_URL}/{note.id}", headers=other_headers)
            foreign_episode = await client.post(
                NOTES_URL,
                json={**payload, "careEpisodeId": other_episode.id},
                headers=owner_headers,
            )
            foreign_medication = await client.post(
                NOTES_URL,
                json={**payload, "medicationId": other_medication.id},
                headers=owner_headers,
            )

        assert other_get.status_code == status.HTTP_404_NOT_FOUND
        assert other_patch.status_code == status.HTTP_404_NOT_FOUND
        assert other_delete.status_code == status.HTTP_404_NOT_FOUND
        assert foreign_episode.status_code == status.HTTP_404_NOT_FOUND
        assert foreign_medication.status_code == status.HTTP_404_NOT_FOUND
        assert await MedicationNote.filter(user=owner).count() == 1

    async def test_deleting_episode_cascades_notes_and_deleting_medication_nulls_reference(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "note-cascade@example.com", "01025000007")
            user = await User.get(email="note-cascade@example.com")
            episode = await create_episode(user, title="2026-09-03 조제약 복약안내")
            medication = await Medication.create(
                care_episode=episode,
                name="삭제될 약",
                times_per_day=1,
                days=7,
            )
            note = await MedicationNote.create(
                user=user,
                care_episode=episode,
                medication=medication,
                dosed_at=datetime(2026, 9, 3, 8, 0),
                body="약이 지워져도 남아야 해요.",
            )

            await medication.delete()
            await note.refresh_from_db()
            assert note.medication_id is None
            await episode.delete()

        assert await MedicationNote.filter(id=note.id).exists() is False
