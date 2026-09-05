"""관리자 이름 규칙. 사용자 회원가입(SignUpRequest.name)과 같은 규칙을 쓴다.

사용자 쪽 규칙 테스트는 app/tests/user_apis/test_name_rules.py 에 있다. 그 파일은
건드리지 않고, 여기서 관리자 두 경로(등록·이름 변경)에 같은 규칙이 걸렸는지만 본다.
"""

from starlette import status
from tortoise.contrib.test import TestCase

from app.models.enums import AdminRole
from app.tests.admin_apis.conftest import auth_header, create_admin, request

ACCOUNTS_URL = "/api/v1/admin/accounts"

# 거부해야 하는 이름. 사용자 쪽과 같은 목록이다.
REJECTED = [
    ("가", "1자"),
    ("가" * 21, "21자"),
    ("스모크2", "숫자 포함"),
    ("김 진형", "가운데 공백"),
    (" 홍길동 ", "앞뒤 공백"),
    ("김철수!", "특수문자"),
    ("김철수\U0001f600", "이모지"),
]

# 통과해야 하는 이름. validate_name 은 모든 언어의 문자를 받는다.
ACCEPTED = ["김진형", "KimJinhyeong", "山田", "홍길"]


class AdminNameRuleTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.super_admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.target = await create_admin(
            name="한지수",
            email="jisu@ozcoding.ai",
            role=AdminRole.STAFF,
            created_by_admin_id=self.super_admin.id,
        )
        self.headers = auth_header(self.super_admin.id)


class TestAdminCreateNameRule(AdminNameRuleTestBase):
    async def test_admin_create_rejects_invalid_name(self) -> None:
        for index, (name, label) in enumerate(REJECTED):
            response = await request(
                "POST",
                ACCOUNTS_URL,
                headers=self.headers,
                json={"name": name, "email": f"reject{index}@ozcoding.ai", "role": "STAFF"},
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label}: {name!r}"

    async def test_admin_create_accepts_letter_only_name(self) -> None:
        for index, name in enumerate(ACCEPTED):
            response = await request(
                "POST",
                ACCOUNTS_URL,
                headers=self.headers,
                json={"name": name, "email": f"accept{index}@ozcoding.ai", "role": "STAFF"},
            )
            assert response.status_code == status.HTTP_201_CREATED, f"{name!r}"


class TestAdminNameUpdateRule(AdminNameRuleTestBase):
    def url(self) -> str:
        return f"{ACCOUNTS_URL}/{self.target.id}/name"

    async def test_admin_name_update_rejects_invalid_name(self) -> None:
        for name, label in REJECTED:
            response = await request("PATCH", self.url(), headers=self.headers, json={"name": name})
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label}: {name!r}"

        await self.target.refresh_from_db()
        assert self.target.name == "한지수"

    async def test_admin_name_update_accepts_letter_only_name(self) -> None:
        for name in ACCEPTED:
            response = await request("PATCH", self.url(), headers=self.headers, json={"name": name})
            assert response.status_code == status.HTTP_200_OK, f"{name!r}"


class TestAdminListQueryHasNoNameRule(AdminNameRuleTestBase):
    """목록 조회의 name·keyword·email 은 「찾으려고 넣는 검색어」다.

    여기에 2자 이상·문자만 규칙을 걸면 한 글자로 검색할 수 없고 「홍」으로 시작하는
    사람을 못 찾는다. 비밀번호 상한을 로그인 칸에 걸면 안 되는 것과 같은 이유다.
    """

    async def test_admin_list_query_accepts_short_keyword(self) -> None:
        for params in ({"name": "김"}, {"keyword": "김"}, {"email": "e"}):
            response = await request("GET", ACCOUNTS_URL, headers=self.headers, params=params)
            assert response.status_code == status.HTTP_200_OK, f"{params}"

    async def test_admin_list_query_accepts_name_with_digit_and_space(self) -> None:
        """규칙 위반 이름으로 저장된 기존 계정도 검색할 수 있어야 한다."""
        for params in ({"name": "관리자3"}, {"name": "일반 관리자"}, {"keyword": "3"}):
            response = await request("GET", ACCOUNTS_URL, headers=self.headers, params=params)
            assert response.status_code == status.HTTP_200_OK, f"{params}"
