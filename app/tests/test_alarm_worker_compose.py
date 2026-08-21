import json
import os
import subprocess
from pathlib import Path


def _load_compose_config() -> dict:
    project_root = Path(__file__).resolve().parents[2]
    compose_env = os.environ.copy()
    compose_env.update(
        {
            "DB_ROOT_PASSWORD": "test",
            "DB_NAME": "test",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DB_EXPOSE_PORT": "3306",
            "DB_PORT": "3306",
            "DOCKER_USER": "test",
            "DOCKER_REPOSITORY": "test",
            "APP_VERSION": "test",
            "AI_WORKER_VERSION": "test",
        }
    )
    result = subprocess.run(
        ["docker", "compose", "config", "--no-env-resolution", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
        env=compose_env,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_alarm_worker_has_required_dependencies():
    compose = _load_compose_config()
    worker = compose["services"]["alarm-worker"]

    assert "app.workers.alarm_worker.WorkerSettings" in str(worker["command"])
    assert set(worker["depends_on"]) >= {"mysql", "redis"}
    assert "ws" in worker["networks"]
    assert worker["environment"]["DB_HOST"] == "mysql"
    assert worker["environment"]["REDIS_HOST"] == "redis"
    assert worker["environment"]["TZ"] == "Asia/Seoul"


def test_fastapi_uses_mysql_service_inside_compose_network():
    compose = _load_compose_config()

    assert compose["services"]["fastapi"]["environment"]["DB_HOST"] == "mysql"
