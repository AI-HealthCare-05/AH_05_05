import json
import subprocess
from pathlib import Path


def test_alarm_worker_has_required_dependencies():
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    compose = json.loads(result.stdout)
    worker = compose["services"]["alarm-worker"]

    assert "app.workers.alarm_worker.WorkerSettings" in str(worker["command"])
    assert set(worker["depends_on"]) >= {"mysql", "redis"}
    assert "ws" in worker["networks"]
    assert worker["environment"]["DB_HOST"] == "mysql"
    assert worker["environment"]["REDIS_HOST"] == "redis"
    assert worker["environment"]["TZ"] == "Asia/Seoul"


def test_fastapi_uses_mysql_service_inside_compose_network():
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    compose = json.loads(result.stdout)

    assert compose["services"]["fastapi"]["environment"]["DB_HOST"] == "mysql"
