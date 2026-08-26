import re

from app.main import app

HANGUL_PATTERN = re.compile(r"[가-힣]")
DOCUMENTED_PREFIXES = ("/api/v1/alarms", "/api/v1/internal/jobs")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def test_alarm_and_job_routes_expose_korean_usage_documentation():
    schema = app.openapi()
    operations = [
        operation
        for path, path_item in schema["paths"].items()
        if path.startswith(DOCUMENTED_PREFIXES)
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    ]

    assert len(operations) == 17
    assert all(HANGUL_PATTERN.search(operation.get("summary", "")) for operation in operations)
    assert all(HANGUL_PATTERN.search(operation.get("description", "")) for operation in operations)


def test_alarm_openapi_exposes_only_the_combined_actions_route():
    paths = app.openapi()["paths"]

    assert "/api/v1/alarms/{alarm_id}/actions" in paths
    assert "/api/v1/alarms/{alarm_id}/pause" not in paths
    assert "/api/v1/alarms/{alarm_id}/resume" not in paths
    assert "/api/v1/alarms/{alarm_id}/complete" not in paths
    assert "/api/v1/alarms/{alarm_id}/skip" not in paths
