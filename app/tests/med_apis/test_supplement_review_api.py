from datetime import date

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.enums import AccountStatus, SupplementStatus
from app.models.supplement_nutrients import (
    SupplementNutrient,
    SupplementReviewReport,
    UserSupplementNutrient,
)
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers, create_supplement


class TestSupplementReviewAPI(TestCase):
    async def _create_registration(
        self,
        client: AsyncClient,
        product: SupplementNutrient | None,
        *,
        index: int,
        name: str,
        score: int | None = None,
        review_body: str | None = None,
        registration_status: SupplementStatus = SupplementStatus.ACTIVE,
        account_status: AccountStatus = AccountStatus.ACTIVE,
    ) -> tuple[User, UserSupplementNutrient, dict[str, str]]:
        email = f"supplement-review-{index}@example.com"
        headers = await authentication_headers(client, email, f"0104{index:07d}")
        user = await User.get(email=email)
        user.name = name
        user.status = account_status
        await user.save(update_fields=["name", "status"])
        registration = await UserSupplementNutrient.create(
            user=user,
            supplement_nutrient=product,
            custom_name=None if product is not None else f"직접 입력 {index}",
            dose_amount="1.000",
            dose_unit="정",
            start_date=date(2026, 9, 1),
            status=registration_status,
            score=score,
            review_body=review_body,
            note="절대 공개하면 안 되는 개인 메모",
        )
        return user, registration, headers

    async def _create_reporter(self, client: AsyncClient, *, index: int) -> User:
        email = f"supplement-reporter-{index}@example.com"
        await authentication_headers(client, email, f"0105{index:07d}")
        return await User.get(email=email)

    async def test_list_reviews_returns_public_fields_and_separate_rating_population(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = await create_supplement("REVIEW-LIST-001", "후기 목록 제품")
            viewer, mine, headers = await self._create_registration(
                client,
                product,
                index=1,
                name="김동훈",
                score=5,
                review_body="내 공개 후기",
                registration_status=SupplementStatus.COMPLETED,
            )
            _, score_only, _ = await self._create_registration(
                client,
                product,
                index=2,
                name="박훈",
                score=4,
            )
            _, body_only, _ = await self._create_registration(
                client,
                product,
                index=3,
                name="KimJinhyeong",
                review_body="본문만 남긴 후기",
            )
            await SupplementReviewReport.create(user=viewer, registration=score_only)
            await self._create_registration(
                client,
                product,
                index=4,
                name="탈퇴회원",
                score=1,
                review_body="보이면 안 됨",
                account_status=AccountStatus.WITHDRAWN,
            )
            _, hidden, _ = await self._create_registration(
                client,
                product,
                index=5,
                name="숨김회원",
                score=1,
                review_body="신고 누적 숨김",
            )
            for index in range(10, 13):
                reporter = await self._create_reporter(client, index=index)
                await SupplementReviewReport.create(user=reporter, registration=hidden)
            await self._create_registration(
                client,
                None,
                index=6,
                name="직접입력",
                score=5,
                review_body="직접 입력 후기",
            )

            response = await client.get(
                f"/api/v1/med/nutr/{product.id}/reviews",
                params={"offset": 0, "limit": 10},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["total"] == 3
        assert payload["review_count"] == 2
        assert payload["rating_average"] == "4.5"
        assert payload["offset"] == 0
        assert payload["limit"] == 10
        assert [item["id"] for item in payload["items"]] == [body_only.id, score_only.id, mine.id]
        assert payload["items"][0] == {
            "id": body_only.id,
            "author_label": "K***g",
            "score": None,
            "review_body": "본문만 남긴 후기",
            "updated_at": payload["items"][0]["updated_at"],
            "is_mine": False,
            "reported_by_me": False,
        }
        assert payload["items"][1]["author_label"] == "박*"
        assert payload["items"][1]["review_body"] is None
        assert payload["items"][1]["reported_by_me"] is True
        assert payload["items"][2]["author_label"] == "김*훈"
        assert payload["items"][2]["is_mine"] is True
        for item in payload["items"]:
            assert set(item) == {
                "id",
                "author_label",
                "score",
                "review_body",
                "updated_at",
                "is_mine",
                "reported_by_me",
            }
            assert "note" not in item
            assert "user_id" not in item
            assert "email" not in item
            assert "report_count" not in item

    async def test_list_reviews_requires_auth_and_validates_pagination(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = await create_supplement("REVIEW-LIST-002", "후기 검증 제품")
            headers = await authentication_headers(client, "review-validation@example.com", "01050000020")
            anonymous = await client.get(f"/api/v1/med/nutr/{product.id}/reviews")
            too_many = await client.get(
                f"/api/v1/med/nutr/{product.id}/reviews",
                params={"limit": 51},
                headers=headers,
            )

        assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
        assert too_many.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_report_is_idempotent_and_rejects_own_review(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = await create_supplement("REVIEW-REPORT-001", "신고 멱등 제품")
            _, target, _ = await self._create_registration(
                client,
                product,
                index=20,
                name="신고대상",
                score=4,
                review_body="신고 가능한 후기",
            )
            _, mine, headers = await self._create_registration(
                client,
                product,
                index=21,
                name="신고자",
                score=5,
                review_body="내 후기",
            )

            reported = await client.post(f"/api/v1/med/nutr/reviews/{target.id}/report", headers=headers)
            duplicate = await client.post(f"/api/v1/med/nutr/reviews/{target.id}/report", headers=headers)
            own = await client.post(f"/api/v1/med/nutr/reviews/{mine.id}/report", headers=headers)

        assert reported.status_code == status.HTTP_204_NO_CONTENT
        assert duplicate.status_code == status.HTTP_204_NO_CONTENT
        assert await SupplementReviewReport.filter(registration=target).count() == 1
        assert own.status_code == status.HTTP_400_BAD_REQUEST
        assert own.json()["detail"] == "본인 후기는 신고할 수 없습니다"

    async def test_report_returns_not_found_for_unavailable_review(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = await create_supplement("REVIEW-REPORT-002", "신고 불가 제품")
            _, empty, _ = await self._create_registration(client, product, index=30, name="빈후기")
            _, withdrawn, _ = await self._create_registration(
                client,
                product,
                index=31,
                name="탈퇴후기",
                score=4,
                account_status=AccountStatus.WITHDRAWN,
            )
            _, hidden, _ = await self._create_registration(
                client,
                product,
                index=32,
                name="숨김후기",
                review_body="숨김 대상",
            )
            for index in range(30, 33):
                reporter = await self._create_reporter(client, index=index)
                await SupplementReviewReport.create(user=reporter, registration=hidden)
            headers = await authentication_headers(client, "review-not-found@example.com", "01050000040")

            responses = [
                await client.post("/api/v1/med/nutr/reviews/999999/report", headers=headers),
                await client.post(f"/api/v1/med/nutr/reviews/{empty.id}/report", headers=headers),
                await client.post(f"/api/v1/med/nutr/reviews/{withdrawn.id}/report", headers=headers),
                await client.post(f"/api/v1/med/nutr/reviews/{hidden.id}/report", headers=headers),
            ]

        assert all(response.status_code == status.HTTP_404_NOT_FOUND for response in responses)

    async def test_third_report_hides_review_from_list_immediately(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = await create_supplement("REVIEW-REPORT-003", "세 번째 신고 제품")
            _, target, _ = await self._create_registration(
                client,
                product,
                index=40,
                name="세번째신고",
                score=5,
                review_body="세 번째 신고 직전",
            )
            for index in range(40, 42):
                reporter = await self._create_reporter(client, index=index)
                await SupplementReviewReport.create(user=reporter, registration=target)
            _, _, headers = await self._create_registration(
                client,
                await create_supplement("REVIEW-REPORT-004", "세 번째 신고자 제품"),
                index=42,
                name="마지막신고자",
            )

            before = await client.get(f"/api/v1/med/nutr/{product.id}/reviews", headers=headers)
            third = await client.post(f"/api/v1/med/nutr/reviews/{target.id}/report", headers=headers)
            after = await client.get(f"/api/v1/med/nutr/{product.id}/reviews", headers=headers)

        assert before.status_code == status.HTTP_200_OK
        assert before.json()["total"] == 1
        assert third.status_code == status.HTTP_204_NO_CONTENT
        assert after.status_code == status.HTTP_200_OK
        assert after.json()["items"] == []
        assert after.json()["total"] == 0
        assert after.json()["rating_average"] is None
        assert after.json()["review_count"] == 0
