from collections.abc import Generator

import pytest


@pytest.fixture(scope="session", autouse=True)
def initialize() -> Generator[None, None]:
    """상위 conftest 의 DB 초기화를 이 디렉터리에서만 무력화한다.

    관리자 조회 API 는 아직 목 데이터만 사용하므로 MySQL 연결이 필요 없다.
    DB 조회로 교체(TODO #10)할 때 이 파일을 지우면 상위 픽스처가 다시 적용된다.
    """
    yield
