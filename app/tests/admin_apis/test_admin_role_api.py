from starlette import status
from tortoise.contrib.test import TestCase

from app.core.exceptions import LastActiveAdminError
from app.dtos.admins import AdminRoleUpdateRequest
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.services.admins import AdminQueryService
from app.tests.admin_apis.conftest import (
    ADMIN_ACCOUNTS_URL,
    auth_header,
    create_admin,
    request,
)


def role_url(admin_id: int) -> str:
    return f"{ADMIN_ACCOUNTS_URL}/{admin_id}/role"


class AdminRoleTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.super_admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.staff = await create_admin(
            name="김진형",
            email="jinhyeong@ozcoding.ai",
            role=AdminRole.STAFF,
            created_by_admin_id=self.super_admin.id,
        )
        self.headers = auth_header(self.super_admin.id)


class TestAdminRoleUpdateAPI(AdminRoleTestBase):
    async def test_promotes_staff_to_admin(self) -> None:
        response = await request("PATCH", role_url(self.staff.id), headers=self.headers, json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"adminId": self.staff.id, "role": "ADMIN"}
        assert (await Admin.get(id=self.staff.id)).role == AdminRole.ADMIN

    async def test_demotes_admin_to_staff(self) -> None:
        # 요청 주체 외에 ADMIN 이 하나 더 있어야 마지막 ADMIN 검사에 걸리지 않는다.
        other = await create_admin(name="임경수", email="kyungsoo@ozcoding.ai", role=AdminRole.ADMIN)

        response = await request("PATCH", role_url(other.id), headers=self.headers, json={"role": "STAFF"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "STAFF"
        assert (await Admin.get(id=other.id)).role == AdminRole.STAFF

    async def test_allows_pending_admin(self) -> None:
        """첫 로그인 전 역할 오지정을 정정할 유일한 경로라 PENDING 은 허용한다."""
        pending = await create_admin(
            name="신동훈",
            email="donghoon@ozcoding.ai",
            role=AdminRole.STAFF,
            status=AccountStatus.PENDING,
        )

        response = await request("PATCH", role_url(pending.id), headers=self.headers, json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_200_OK
        assert (await Admin.get(id=pending.id)).role == AdminRole.ADMIN

    async def test_rejects_unknown_admin(self) -> None:
        response = await request("PATCH", role_url(999999), headers=self.headers, json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "ADMIN_NOT_FOUND"

    async def test_rejects_own_role_change(self) -> None:
        """스스로를 낮추면 되돌릴 API 에도 접근할 수 없어 복구 수단이 없다."""
        response = await request("PATCH", role_url(self.super_admin.id), headers=self.headers, json={"role": "STAFF"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_CHANGE_OWN_ROLE"
        assert (await Admin.get(id=self.super_admin.id)).role == AdminRole.ADMIN

    async def test_rejects_same_role(self) -> None:
        response = await request("PATCH", role_url(self.staff.id), headers=self.headers, json={"role": "STAFF"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "SAME_ROLE"

    async def test_demoting_other_admin_keeps_caller_as_active_admin(self) -> None:
        """주체가 활성 ADMIN 이므로 남의 강등만으로는 활성 ADMIN 이 0명이 되지 않는다."""
        other = await create_admin(name="임경수", email="kyungsoo@ozcoding.ai", role=AdminRole.ADMIN)

        response = await request("PATCH", role_url(other.id), headers=self.headers, json={"role": "STAFF"})

        assert response.status_code == status.HTTP_200_OK
        assert await Admin.filter(role=AdminRole.ADMIN, status=AccountStatus.ACTIVE).count() == 1

    async def test_rejects_suspended_admin(self) -> None:
        suspended = await create_admin(
            name="한지수",
            email="jisu@ozcoding.ai",
            role=AdminRole.STAFF,
            status=AccountStatus.SUSPENDED,
        )

        response = await request("PATCH", role_url(suspended.id), headers=self.headers, json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_CHANGE_INACTIVE_ADMIN"
        assert (await Admin.get(id=suspended.id)).role == AdminRole.STAFF

    async def test_rejects_withdrawn_admin(self) -> None:
        withdrawn = await create_admin(
            name="탈퇴자",
            email="left@ozcoding.ai",
            role=AdminRole.STAFF,
            status=AccountStatus.WITHDRAWN,
        )

        response = await request("PATCH", role_url(withdrawn.id), headers=self.headers, json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_CHANGE_INACTIVE_ADMIN"

    async def test_rejects_role_outside_enum(self) -> None:
        response = await request("PATCH", role_url(self.staff.id), headers=self.headers, json={"role": "OWNER"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_staff_caller(self) -> None:
        response = await request(
            "PATCH",
            role_url(self.super_admin.id),
            headers=auth_header(self.staff.id),
            json={"role": "STAFF"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_rejects_missing_token(self) -> None:
        response = await request("PATCH", role_url(self.staff.id), json={"role": "ADMIN"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"


class TestLastActiveAdminInvariant(AdminRoleTestBase):
    """마지막 활성 ADMIN 강등 금지.

    단일 요청 기준으로는 HTTP 경로로 도달하지 않는다. 주체가 ACTIVE ADMIN 이어야 이 API 를
    부를 수 있고(require_admin) 본인은 CANNOT_CHANGE_OWN_ROLE 로 먼저 막히므로, 남을
    강등해도 주체 자신이 활성 ADMIN 으로 남는다.

    그래도 검사가 필요하다. ACTIVE ADMIN 이 2명일 때 두 사람이 동시에 서로를 강등하면
    각자의 카운트 쿼리가 상대의 커밋 전 스냅샷을 보고 둘 다 통과할 수 있다(MVCC).
    본인 강등을 나중에 허용하거나 배치·스크립트가 서비스를 직접 부르는 경우도 그렇다.

    동시 요청은 테스트로 재현하기 어려워, 검사 자체가 살아 있는지를 서비스 계층 호출로
    고정한다. 자세한 배경은 _ensure_active_admin_remains_after_role_change 독스트링에 있다.
    """

    async def test_service_rejects_demoting_the_only_active_admin(self) -> None:
        service = AdminQueryService()

        with self.assertRaises(LastActiveAdminError):
            # 주체를 STAFF 로 둔다. HTTP 라면 require_admin 에서 403 이지만, 서비스 계층
            # 검사가 주체의 역할과 무관하게 동작하는지 보는 것이 이 테스트의 목적이다.
            await service.update_role(
                self.super_admin.id,
                AdminRoleUpdateRequest(role=AdminRole.STAFF),
                actor_admin_id=self.staff.id,
            )

        assert (await Admin.get(id=self.super_admin.id)).role == AdminRole.ADMIN


class TestAdminRoleTakesEffectImmediately(AdminRoleTestBase):
    """강등이 다음 요청부터 즉시 반영되는지 고정한다.

    권한 검사가 매 요청 DB 를 조회하므로(dependencies/admin.py 의 _authenticate) 이미
    발급된 액세스 토큰으로도 ADMIN 전용 API 를 쓸 수 없다. 나중에 누가 성능을 이유로
    role 을 토큰 클레임에 캐시하면 이 테스트가 잡아준다.
    """

    async def test_demoted_admin_loses_admin_apis_with_same_token(self) -> None:
        target = await create_admin(name="임경수", email="kyungsoo@ozcoding.ai", role=AdminRole.ADMIN)
        target_token = auth_header(target.id)

        # 강등 전에는 ADMIN 전용 API 가 통한다
        before = await request("GET", ADMIN_ACCOUNTS_URL, headers=target_token, params={"page": 1, "size": 10})
        assert before.status_code == status.HTTP_200_OK
        created = await request(
            "POST",
            ADMIN_ACCOUNTS_URL,
            headers=target_token,
            json={"name": "테스트", "email": "temp@ozcoding.ai", "role": "STAFF", "isActive": True},
        )
        assert created.status_code == status.HTTP_201_CREATED

        # super_admin 이 target 을 STAFF 로 강등한다
        demoted = await request("PATCH", role_url(target.id), headers=self.headers, json={"role": "STAFF"})
        assert demoted.status_code == status.HTTP_200_OK

        # 같은 토큰으로 ADMIN 전용 API 를 부르면 즉시 403 이다
        after = await request(
            "POST",
            ADMIN_ACCOUNTS_URL,
            headers=target_token,
            json={"name": "테스트2", "email": "temp2@ozcoding.ai", "role": "STAFF", "isActive": True},
        )
        assert after.status_code == status.HTTP_403_FORBIDDEN

        # 조회는 STAFF 도 허용이라 그대로 통한다(권한 매트릭스)
        still_readable = await request("GET", ADMIN_ACCOUNTS_URL, headers=target_token, params={"page": 1, "size": 10})
        assert still_readable.status_code == status.HTTP_200_OK
