from datetime import date, datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.supplement_nutrients import NutrientStandard
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers, create_supplement

STANDARD_NUTRIENT_KEYS = {
    "protein_g",
    "carb_g",
    "fat_g",
    "fiber_g",
    "calcium_mg",
    "iron_mg",
    "phosphorus_mg",
    "potassium_mg",
    "sodium_mg",
    "vitamin_a_ug_rae",
    "thiamine_mg",
    "riboflavin_mg",
    "niacin_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
}


def registration_payload(*, slots: list[str] | None = None) -> dict:
    return {
        "dose_amount": "1.000",
        "dose_unit": "정",
        "start_date": "2026-08-24",
        "slots": slots or ["MORNING", "EVENING"],
        "note": "식후 복용",
    }


def manual_registration_payload(*, custom_name: str = "직접 입력 오메가3") -> dict:
    return {
        "custom_name": custom_name,
        "dose_amount": "1.000",
        "dose_unit": "캡슐",
        "start_date": "2026-09-01",
        "end_date": None,
        "slots": ["MORNING"],
        "note": None,
    }


async def get_active_supplement_list(client: AsyncClient, headers: dict[str, str]):
    return await client.get(
        "/api/v1/med/user-suppl-nutr",
        params={"status": "ACTIVE", "offset": 0, "limit": 20},
        headers=headers,
    )


class TestUserSupplementNutrientAPI(TestCase):
    async def test_create_manual_returns_registration_without_supplement(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-create@example.com", "01021000030")

            response = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(),
                headers=headers,
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["custom_name"] == "직접 입력 오메가3"
        assert response.json()["supplement"] is None
        assert response.json()["status"] == "ACTIVE"
        assert response.json()["slots"] == [{"slot": "MORNING", "time": "08:00:00"}]

    async def test_create_manual_allows_duplicate_names(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-duplicate@example.com", "01021000031")

            first = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(custom_name="같은 이름"),
                headers=headers,
            )
            second = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(custom_name="같은 이름"),
                headers=headers,
            )
            listed = await get_active_supplement_list(client, headers)

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert first.json()["id"] != second.json()["id"]
        assert listed.json()["total"] == 2

    async def test_manual_registration_appears_in_list(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-list@example.com", "01021000032")
            created = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(custom_name="목록 직접 입력"),
                headers=headers,
            )

            listed = await get_active_supplement_list(client, headers)

        assert created.status_code == status.HTTP_201_CREATED
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["custom_name"] == "목록 직접 입력"
        assert listed.json()["items"][0]["supplement"] is None

    async def test_manual_registration_can_be_updated_and_completed(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-manage@example.com", "01021000033")
            created = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(custom_name="관리할 직접 입력"),
                headers=headers,
            )
            registration_id = created.json()["id"]
            detail = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            updated = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"dose_amount": "2.000", "slots": ["BEDTIME"], "note": "취침 전"},
                headers=headers,
            )
            completed = await client.delete(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            after_complete = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )

        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["supplement"] is None
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["custom_name"] == "관리할 직접 입력"
        assert updated.json()["dose_amount"] == "2.000"
        assert updated.json()["slots"] == [{"slot": "BEDTIME", "time": "22:00:00"}]
        assert completed.status_code == status.HTTP_204_NO_CONTENT
        assert after_complete.json()["status"] == "COMPLETED"
        assert after_complete.json()["supplement"] is None

    async def test_create_manual_rejects_empty_name(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-empty@example.com", "01021000034")

            for custom_name in ("", "   "):
                response = await client.post(
                    "/api/v1/med/user-suppl-nutr",
                    json=manual_registration_payload(custom_name=custom_name),
                    headers=headers,
                )

                assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
                assert response.json()["field"] == "custom_name"

    async def test_upsert_still_requires_product_id(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "manual-put-regression@example.com", "01021000035")

            response = await client.put(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(),
                headers=headers,
            )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    async def test_nutrient_standard_still_returned_with_manual_rows(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(
            grp="여자",
            age="19-29세",
            calcium_mg_rni="800",
            calcium_mg_ul="2500",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "manual-standard@example.com"
            headers = await authentication_headers(client, email, "01021000036")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            created = await client.post(
                "/api/v1/med/user-suppl-nutr",
                json=manual_registration_payload(),
                headers=headers,
            )

            listed = await get_active_supplement_list(client, headers)

        assert created.status_code == status.HTTP_201_CREATED
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["items"][0]["supplement"] is None
        assert listed.json()["nutrient_standard"]["calcium_mg"] == {
            "rni": "800.000",
            "ai": None,
            "ul": "2500.000",
        }

    async def test_patch_sets_score_and_list_includes_it(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-score-list@example.com", "01021000021")
            product = await create_supplement("USER-SUPPL-SCORE-001", "별점 목록 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )

            updated = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{created.json()['id']}",
                json={"score": 4},
                headers=headers,
            )
            listed = await get_active_supplement_list(client, headers)

        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["score"] == 4
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["items"][0]["score"] == 4

    async def test_patch_can_clear_score(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-score-clear@example.com", "01021000022")
            product = await create_supplement("USER-SUPPL-SCORE-002", "별점 삭제 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"score": 4},
                headers=headers,
            )

            cleared = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"score": None},
                headers=headers,
            )

        assert cleared.status_code == status.HTTP_200_OK
        assert cleared.json()["score"] is None

    async def test_patch_without_score_preserves_score(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-score-preserve@example.com", "01021000023")
            product = await create_supplement("USER-SUPPL-SCORE-003", "별점 유지 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"score": 5},
                headers=headers,
            )

            updated = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"note": "별점은 유지"},
                headers=headers,
            )

        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["score"] == 5
        assert updated.json()["note"] == "별점은 유지"

    async def test_patch_rejects_score_outside_one_to_five(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-score-invalid@example.com", "01021000026")
            product = await create_supplement("USER-SCORE-INVALID", "별점 범위 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )

            invalid_scores = {
                0: "Input should be greater than or equal to 1",
                6: "Input should be less than or equal to 5",
                -1: "Input should be greater than or equal to 1",
            }
            for score, message in invalid_scores.items():
                response = await client.patch(
                    f"/api/v1/med/user-suppl-nutr/{created.json()['id']}",
                    json={"score": score},
                    headers=headers,
                )

                assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
                assert response.json() == {
                    "code": "VALIDATION_ERROR",
                    "message": message,
                    "field": "score",
                }

    async def test_reregistering_completed_supplement_preserves_score(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-score-reregister@example.com", "01021000024")
            product = await create_supplement("USER-SUPPL-SCORE-004", "별점 재등록 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"score": 5},
                headers=headers,
            )
            completed = await client.delete(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )

            reregistered = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["LUNCH"]),
                headers=headers,
            )

        assert completed.status_code == status.HTTP_204_NO_CONTENT
        assert reregistered.status_code == status.HTTP_200_OK
        assert reregistered.json()["id"] == registration_id
        assert reregistered.json()["status"] == "ACTIVE"
        assert reregistered.json()["score"] == 5

    async def test_patch_review_body_normalizes_text_and_preserves_other_fields(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-review-patch@example.com", "01021000027")
            product = await create_supplement("USER-REVIEW-001", "후기 수정 영양제")
            payload = registration_payload()
            payload["note"] = "개인 메모"
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=payload,
                headers=headers,
            )
            registration_id = created.json()["id"]

            reviewed = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"review_body": "  공개 후기예요  "},
                headers=headers,
            )
            cleared = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"review_body": "   "},
                headers=headers,
            )

        assert reviewed.status_code == status.HTTP_200_OK
        assert reviewed.json()["review_body"] == "공개 후기예요"
        assert reviewed.json()["note"] == "개인 메모"
        assert cleared.status_code == status.HTTP_200_OK
        assert cleared.json()["review_body"] is None
        assert cleared.json()["note"] == "개인 메모"

    async def test_reregistering_completed_supplement_preserves_review_body(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-review-reregister@example.com", "01021000028")
            product = await create_supplement("USER-REVIEW-002", "후기 재등록 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"score": 4, "review_body": "다 먹고 남긴 후기"},
                headers=headers,
            )
            await client.delete(f"/api/v1/med/user-suppl-nutr/{registration_id}", headers=headers)

            reregistered = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["LUNCH"]),
                headers=headers,
            )

        assert reregistered.status_code == status.HTTP_200_OK
        assert reregistered.json()["id"] == registration_id
        assert reregistered.json()["score"] == 4
        assert reregistered.json()["review_body"] == "다 먹고 남긴 후기"

    async def test_patch_can_set_and_clear_note(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "suppl-note-regression@example.com", "01021000025")
            product = await create_supplement("USER-SUPPL-NOTE-001", "메모 회귀 영양제")
            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            noted = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"note": "저녁 식후"},
                headers=headers,
            )
            cleared = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"note": None},
                headers=headers,
            )

        assert noted.status_code == status.HTTP_200_OK
        assert noted.json()["note"] == "저녁 식후"
        assert cleared.status_code == status.HTTP_200_OK
        assert cleared.json()["note"] is None

    async def test_list_includes_nutrient_standard(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(
            grp="여자",
            age="19-29세",
            calcium_mg_rni="800",
            calcium_mg_ul="2500",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-standard@example.com"
            headers = await authentication_headers(client, email, "01021000011")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        standard = response.json()["nutrient_standard"]
        assert standard["grp"] == "여자"
        assert standard["age"] == "19-29세"
        assert standard["calcium_mg"] == {"rni": "800.000", "ai": None, "ul": "2500.000"}

    async def test_list_standard_is_null_without_birth_date(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-no-birth-date@example.com"
            headers = await authentication_headers(client, email, "01021000012")
            user = await User.get(email=email)
            user.birth_date = None
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_is_null_without_gender(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-no-gender@example.com"
            headers = await authentication_headers(client, email, "01021000013")
            user = await User.get(email=email)
            user.gender = None
            await user.save(update_fields=["gender"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_is_null_when_row_missing(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(
                client,
                "user-suppl-missing-standard@example.com",
                "01021000014",
            )
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_keys_are_always_present(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(grp="여자", age="19-29세")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-standard-keys@example.com"
            headers = await authentication_headers(client, email, "01021000015")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        standard = response.json()["nutrient_standard"]
        assert set(standard) == {"grp", "age", *STANDARD_NUTRIENT_KEYS}
        for nutrient_key in STANDARD_NUTRIENT_KEYS:
            assert standard[nutrient_key] == {"rni": None, "ai": None, "ul": None}

    async def test_list_standard_never_matches_pregnant_group(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(
            grp="임신부",
            age="19-29세",
            calcium_mg_rni="900",
        )
        await NutrientStandard.create(
            grp="수유부",
            age="19-29세",
            calcium_mg_rni="1000",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-never-pregnant@example.com"
            headers = await authentication_headers(client, email, "01021000016")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_authenticated_user_can_manage_own_supplement_registration(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "user-suppl@example.com", "01021000001")
            product = await create_supplement("USER-SUPPL-001", "사용자 철분")

            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            listed = await client.get(
                "/api/v1/med/user-suppl-nutr",
                params={"status": "ACTIVE", "offset": 0, "limit": 20},
                headers=headers,
            )
            detail = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            updated = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"dose_amount": "2.000", "slots": ["BEDTIME"], "note": "취침 전"},
                headers=headers,
            )
            completed = await client.delete(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            after_complete = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )

        assert created.status_code == status.HTTP_200_OK
        assert created.json()["supplement"]["id"] == product.id
        assert [item["slot"] for item in created.json()["slots"]] == ["MORNING", "EVENING"]
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 1
        assert detail.status_code == status.HTTP_200_OK
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["dose_amount"] == "2.000"
        assert updated.json()["slots"] == [{"slot": "BEDTIME", "time": "22:00:00"}]
        assert completed.status_code == status.HTTP_204_NO_CONTENT
        assert after_complete.json()["status"] == "COMPLETED"
        assert after_complete.json()["end_date"] is not None

    async def test_registration_is_upserted_and_is_owner_scoped(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_headers = await authentication_headers(client, "suppl-owner-api@example.com", "01021000002")
            other_headers = await authentication_headers(client, "suppl-other-api@example.com", "01021000003")
            product = await create_supplement("USER-SUPPL-002", "사용자 비타민")

            first = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["LUNCH"]),
                headers=owner_headers,
            )
            second = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["BEDTIME"]),
                headers=owner_headers,
            )
            hidden = await client.get(
                f"/api/v1/med/user-suppl-nutr/{first.json()['id']}",
                headers=other_headers,
            )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.json()["id"] == second.json()["id"]
        assert hidden.status_code == status.HTTP_404_NOT_FOUND

    async def test_routes_require_authentication_and_are_exposed_in_openapi(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.get("/api/v1/med/user-suppl-nutr")
            openapi = (await client.get("/api/openapi.json")).json()

        assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
        assert "/api/v1/med/user-suppl-nutr" in openapi["paths"]
        assert "post" in openapi["paths"]["/api/v1/med/user-suppl-nutr"]
        assert "/api/v1/med/user-suppl-nutr/{registration_id}" in openapi["paths"]
        assert set(openapi["paths"]["/api/v1/med/user-suppl-nutr/{registration_id}"]) >= {
            "get",
            "put",
            "patch",
            "delete",
        }
