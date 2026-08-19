from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.main import app


def test_root_serves_static_index_after_api_routes() -> None:
    api_route_index = next(
        index for index, route in enumerate(app.routes) if getattr(route, "path", "") == "/api/v1/auth/signup"
    )
    static_route_index, static_mount = next(
        (index, route) for index, route in enumerate(app.routes) if isinstance(route, Mount) and route.path == ""
    )

    assert api_route_index < static_route_index
    assert isinstance(static_mount.app, StaticFiles)

    response = TestClient(static_mount.app).get("/")

    assert response.status_code == 200
    assert "관리자 로그인" in response.text
