"""정적 파일 응답의 캐시 헤더.

이 헤더가 없으면 브라우저가 heuristic caching 으로 재검증 없이 옛 파일을 쓴다.
실제로 화면 수정이 반영되지 않아 하드 리로드가 필요했고 회원 상세 보기가 깨졌다(#118).
누가 이 헤더를 지우면 CI 가 잡아야 하므로 app/tests/ 에 둔다
(루트 tests/ 는 CI 에서 실행되지 않는다 — #125).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

# CSS·JS·오버레이 HTML 을 각각 한 개씩 본다. 종류마다 Starlette 가 다른 content-type 을
# 붙이지만 캐시 정책은 같아야 한다.
STATIC_PATHS = [
    "/css/management.css",
    "/js/api.js",
    "/templates/overlay-user-detail.html",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", STATIC_PATHS)
def test_static_response_disables_heuristic_caching(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", STATIC_PATHS)
def test_static_response_keeps_validators(client: TestClient, path: str) -> None:
    """no-cache 는 매번 재검증을 뜻하므로 etag 가 없으면 매번 전체를 다시 받는다."""
    response = client.get(path)

    assert response.headers.get("etag")
    assert response.headers.get("last-modified")


@pytest.mark.parametrize("path", STATIC_PATHS)
def test_conditional_request_returns_not_modified(client: TestClient, path: str) -> None:
    etag = client.get(path).headers["etag"]

    response = client.get(path, headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert not response.content


@pytest.mark.parametrize("path", STATIC_PATHS)
def test_not_modified_response_also_disables_heuristic_caching(client: TestClient, path: str) -> None:
    """304 에도 헤더가 있어야 한다.

    없으면 브라우저가 그 다음 요청부터 다시 heuristic caching 으로 돌아간다.
    200 만 검사하면 절반만 보장된다.
    """
    etag = client.get(path).headers["etag"]

    response = client.get(path, headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.headers["cache-control"] == "no-cache"
