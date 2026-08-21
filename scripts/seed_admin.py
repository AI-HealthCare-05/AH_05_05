"""초기 ADMIN 계정을 만든다.

관리자 계정은 자체 가입이 없고 ADMIN 이 생성한다(REQ-ADMIN-008). 따라서 최초 1명은
이 스크립트로 넣어야 하며, 그 계정만 created_by_admin_id 가 NULL 이다.

    uv run python -m scripts.seed_admin

저장소 루트에서 -m 으로 실행한다. `python scripts/seed_admin.py` 로 실행하면
sys.path 기준이 scripts/ 가 되어 app 패키지를 찾지 못한다.

SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD 를 .env 또는 환경변수로 넘긴다.
이미 ADMIN 이 하나라도 있으면 아무것도 하지 않으므로 반복 실행해도 안전하다.
"""

import asyncio
import sys

from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.core.utils.security import hash_password
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole


async def seed_admin() -> int:
    email = config.SUPERADMIN_EMAIL
    password = config.SUPERADMIN_PASSWORD

    if not email or not password:
        print("SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD 가 설정되지 않았습니다.")
        print("envs/example.local.env 를 참고해 .env 에 추가하세요.")
        return 1

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        # 중복 실행 방지. 운영 중인 DB 에 두 번째 계정을 만들지 않는다.
        if await Admin.exists(role=AdminRole.ADMIN):
            print("ADMIN 계정이 이미 존재합니다. 아무것도 하지 않고 종료합니다.")
            return 0

        admin = await Admin.create(
            email=email,
            # 평문은 저장하지 않는다.
            hashed_password=hash_password(password),
            name="관리자",
            role=AdminRole.ADMIN,
            status=AccountStatus.ACTIVE,
            # 최초 ADMIN 은 생성자가 없다.
            created_by_admin_id=None,
        )
        print(f"초기 ADMIN 생성 완료: id={admin.id} email={admin.email}")
        print("보안을 위해 로그인 후 비밀번호를 변경하고 .env 의 SUPERADMIN_PASSWORD 를 지우세요.")
        return 0
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    sys.exit(asyncio.run(seed_admin()))
