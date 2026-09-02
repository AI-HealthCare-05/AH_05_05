from datetime import datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.enums import AccountStatus, SupplementStatus
from app.models.supplement_nutrients import SupplementReviewReport, UserSupplementNutrient
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers, create_supplement


class TestMedNutrAPI(TestCase):
    async def _create_registration(
        self,
        client: AsyncClient,
        product_id: int | None,
        *,
        index: int,
        score: int | None = None,
        registration_status: SupplementStatus = SupplementStatus.ACTIVE,
        account_status: AccountStatus = AccountStatus.ACTIVE,
    ) -> UserSupplementNutrient:
        email = f"nutr-sort-{index}@example.com"
        await authentication_headers(client, email, f"0103{index:07d}")
        user = await User.get(email=email)
        if user.status != account_status:
            user.status = account_status
            await user.save(update_fields=["status"])
        return await UserSupplementNutrient.create(
            user=user,
            supplement_nutrient_id=product_id,
            custom_name=None if product_id is not None else f"직접 입력 {index}",
            dose_amount="1.000",
            dose_unit="정",
            start_date=datetime.now(config.TIMEZONE).date(),
            status=registration_status,
            score=score,
        )

    async def _create_popularity_rows(self, user: User, *, manual_count: int):
        today = datetime.now(config.TIMEZONE).date()
        products = [await create_supplement(f"POPULAR-{index}", f"인기 표준 제품 {index}") for index in range(5)]
        for product in products:
            await UserSupplementNutrient.create(
                user=user,
                supplement_nutrient=product,
                dose_amount="1.000",
                dose_unit="정",
                start_date=today,
            )
        for index in range(manual_count):
            await UserSupplementNutrient.create(
                user=user,
                supplement_nutrient_id=None,
                custom_name=f"직접 입력 제품 {index}",
                dose_amount="1.000",
                dose_unit="정",
                start_date=today,
            )
        return products

    async def test_name_contains_search_is_paginated_and_case_insensitive(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-search@example.com", "01020000001")
            await create_supplement("FOOD-001", "철분 프리미엄")
            await create_supplement("FOOD-002", "고함량 철분")
            await create_supplement("FOOD-003", "VITAMIN D 1000")

            listed = await client.get(
                "/api/v1/med/nutr",
                params={"name": "철분", "offset": 0, "limit": 1},
                headers=headers,
            )
            english = await client.get(
                "/api/v1/med/nutr",
                params={"name": "vitamin"},
                headers=headers,
            )

        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 2
        assert listed.json()["offset"] == 0
        assert listed.json()["limit"] == 1
        assert len(listed.json()["items"]) == 1
        assert english.status_code == status.HTTP_200_OK
        assert english.json()["items"][0]["name"] == "VITAMIN D 1000"

    async def test_detail_returns_full_nutrition_and_missing_product_is_404(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-detail@example.com", "01020000002")
            product = await create_supplement("FOOD-010", "상세 영양제")

            detail = await client.get(f"/api/v1/med/nutr/{product.id}", headers=headers)
            missing = await client.get("/api/v1/med/nutr/999999", headers=headers)

        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["food_code"] == "FOOD-010"
        assert detail.json()["basis_qty"] == "500mg"
        assert detail.json()["protein_g"] == "0.00"
        assert detail.json()["water_g"] is None
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        assert missing.json()["detail"] == "Supplement nutrient not found."

    async def test_catalog_requires_authentication_and_non_blank_name(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.get("/api/v1/med/nutr", params={"name": "철분"})
            headers = await authentication_headers(client, "nutr-validation@example.com", "01020000003")
            blank = await client.get("/api/v1/med/nutr", params={"name": "   "}, headers=headers)

        assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
        assert blank.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_popular_excludes_manual_registrations(self) -> None:
        email = "popular-excludes-manual@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, email, "01020000004")
            user = await User.get(email=email)
            products = await self._create_popularity_rows(user, manual_count=1)

            response = await client.get("/api/v1/med/nutr/popular", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.json()] == [product.id for product in products]

    async def test_popular_returns_five_when_manual_rows_dominate(self) -> None:
        email = "popular-manual-dominates@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, email, "01020000005")
            user = await User.get(email=email)
            products = await self._create_popularity_rows(user, manual_count=6)

            response = await client.get("/api/v1/med/nutr/popular", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 5
        assert {item["id"] for item in response.json()} == {product.id for product in products}

    async def test_search_default_sort_is_name(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-name@example.com", "01020000006")
            await create_supplement("SORT-NAME-2", "정렬 제품 나")
            await create_supplement("SORT-NAME-1", "정렬 제품 가")

            response = await client.get("/api/v1/med/nutr", params={"name": "정렬 제품"}, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert [item["name"] for item in response.json()["items"]] == ["정렬 제품 가", "정렬 제품 나"]

    async def test_search_sort_by_rating_puts_null_last(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-rating@example.com", "01020000007")
            unrated = await create_supplement("SORT-RATING-1", "평점 정렬 가 미평가")
            rated = await create_supplement("SORT-RATING-2", "평점 정렬 나 평가")
            await self._create_registration(client, rated.id, index=101, score=4)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "평점 정렬", "sort": "rating"},
                headers=headers,
            )

        items = response.json()["items"]
        assert [item["id"] for item in items] == [rated.id, unrated.id]
        assert items[0]["rating_average"] == "4.0"
        assert items[0]["review_count"] == 1
        assert items[1]["rating_average"] is None
        assert items[1]["review_count"] == 0

    async def test_search_sort_by_rating_breaks_tie_by_review_count(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-rating-tie@example.com", "01020000008")
            one_review = await create_supplement("SORT-TIE-1", "동률 제품 가 한개")
            three_reviews = await create_supplement("SORT-TIE-2", "동률 제품 나 세개")
            await self._create_registration(client, one_review.id, index=111, score=5)
            for index in range(112, 115):
                await self._create_registration(client, three_reviews.id, index=index, score=5)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "동률 제품", "sort": "rating"},
                headers=headers,
            )

        items = response.json()["items"]
        assert [item["id"] for item in items] == [three_reviews.id, one_review.id]
        assert [item["review_count"] for item in items] == [3, 1]

    async def test_search_sort_by_reviews_uses_review_count(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-reviews@example.com", "01020000009")
            one_review = await create_supplement("SORT-REVIEWS-1", "후기순 제품 가 한개")
            two_reviews = await create_supplement("SORT-REVIEWS-2", "후기순 제품 나 두개")
            await self._create_registration(client, one_review.id, index=121, score=5)
            await self._create_registration(client, two_reviews.id, index=122, score=3)
            await self._create_registration(client, two_reviews.id, index=123, score=4)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "후기순 제품", "sort": "reviews"},
                headers=headers,
            )

        assert [item["id"] for item in response.json()["items"]] == [two_reviews.id, one_review.id]

    async def test_search_sort_excludes_manual_registrations(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-manual@example.com", "01020000010")
            product = await create_supplement("SORT-MANUAL-1", "직접 입력 제외 제품")
            await self._create_registration(client, product.id, index=131, score=3)
            await self._create_registration(client, None, index=132, score=5)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "직접 입력 제외", "sort": "rating"},
                headers=headers,
            )

        item = response.json()["items"][0]
        assert item["rating_average"] == "3.0"
        assert item["review_count"] == 1

    async def test_search_sort_by_registered_counts_active_only(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-registered@example.com", "01020000011")
            inactive_heavy = await create_supplement("SORT-REGISTERED-1", "등록순 제품 가 비활성")
            active_heavy = await create_supplement("SORT-REGISTERED-2", "등록순 제품 나 활성")
            await self._create_registration(client, inactive_heavy.id, index=141)
            for index in range(142, 145):
                await self._create_registration(
                    client,
                    inactive_heavy.id,
                    index=index,
                    registration_status=SupplementStatus.COMPLETED,
                )
            await self._create_registration(client, active_heavy.id, index=145)
            await self._create_registration(client, active_heavy.id, index=146)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "등록순 제품", "sort": "registered"},
                headers=headers,
            )

        assert [item["id"] for item in response.json()["items"]] == [active_heavy.id, inactive_heavy.id]

    async def test_search_response_includes_rating_and_count(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-response@example.com", "01020000012")
            await create_supplement("SORT-RESPONSE-1", "집계 응답 제품")

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "집계 응답"},
                headers=headers,
            )

        item = response.json()["items"][0]
        assert item["rating_average"] is None
        assert item["review_count"] == 0

    async def test_search_rating_excludes_withdrawn_and_three_report_hidden_reviews(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-public-review@example.com", "01020000014")
            product = await create_supplement("SORT-PUBLIC-REVIEW", "공개 후기 집계 제품")
            await self._create_registration(client, product.id, index=151, score=5)
            await self._create_registration(
                client,
                product.id,
                index=152,
                score=1,
                account_status=AccountStatus.WITHDRAWN,
            )
            hidden = await self._create_registration(client, product.id, index=153, score=2)
            await self._create_registration(
                client,
                product.id,
                index=154,
                score=3,
                registration_status=SupplementStatus.COMPLETED,
            )
            for index in range(155, 158):
                await authentication_headers(client, f"reporter-{index}@example.com", f"0103{index:07d}")
                reporter = await User.get(email=f"reporter-{index}@example.com")
                await SupplementReviewReport.create(user=reporter, registration=hidden)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "공개 후기 집계", "sort": "rating"},
                headers=headers,
            )

        item = response.json()["items"][0]
        assert item["rating_average"] == "4.0"
        assert item["review_count"] == 2

    async def test_search_rating_without_reports_keeps_unreviewed_product(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-no-report@example.com", "01020000015")
            rated = await create_supplement("SORT-NO-REPORT-1", "신고 없음 평가 제품")
            unreviewed = await create_supplement("SORT-NO-REPORT-2", "신고 없음 미평가 제품")
            await self._create_registration(client, rated.id, index=158, score=4)

            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "신고 없음", "sort": "rating"},
                headers=headers,
            )

        items = response.json()["items"]
        assert [item["id"] for item in items] == [rated.id, unreviewed.id]
        assert items[0]["rating_average"] == "4.0"
        assert items[0]["review_count"] == 1
        assert items[1]["rating_average"] is None
        assert items[1]["review_count"] == 0

    async def test_search_rejects_unknown_sort(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "sort-invalid@example.com", "01020000013")
            response = await client.get(
                "/api/v1/med/nutr",
                params={"name": "제품", "sort": "popular"},
                headers=headers,
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
