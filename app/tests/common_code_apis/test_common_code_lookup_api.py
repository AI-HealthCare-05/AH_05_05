from starlette import status
from tortoise.contrib.test import TestCase

from app.models.common_codes import CommonCode, CommonCodeGroup
from app.tests.admin_apis.conftest import request


class TestCommonCodeLookupAPI(TestCase):
    async def test_lookup_returns_only_active_codes_in_active_group_in_sort_order(self) -> None:
        group = await CommonCodeGroup.create(
            category="CHAT",
            group_code="P_REASON",
            group_name="긍정 평가 사유",
        )
        second = await CommonCode.create(
            group=group,
            detail_code="CLEAR",
            detail_name="설명이 명확해요",
            sort_order=2,
        )
        first = await CommonCode.create(
            group=group,
            detail_code="HELPFUL",
            detail_name="도움이 되었어요",
            sort_order=1,
        )
        await CommonCode.create(
            group=group,
            detail_code="HIDDEN",
            detail_name="숨김",
            sort_order=0,
            is_active=False,
        )

        response = await request("GET", "/api/v1/common-codes/chat/p_reason")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "category": "CHAT",
            "group_code": "P_REASON",
            "group_name": "긍정 평가 사유",
            "items": [
                {"id": first.id, "detail_code": "HELPFUL", "detail_name": "도움이 되었어요", "sort_order": 1},
                {"id": second.id, "detail_code": "CLEAR", "detail_name": "설명이 명확해요", "sort_order": 2},
            ],
        }

    async def test_lookup_returns_not_found_for_inactive_group(self) -> None:
        await CommonCodeGroup.create(
            category="CHAT",
            group_code="N_REASON",
            group_name="부정 평가 사유",
            is_active=False,
        )

        response = await request("GET", "/api/v1/common-codes/CHAT/N_REASON")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "COMMON_CODE_GROUP_NOT_FOUND"
