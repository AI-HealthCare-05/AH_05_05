import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


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
    with TemporaryDirectory() as temp_dir:
        compose_root = Path(temp_dir)
        shutil.copy2(project_root / "docker-compose.yml", compose_root / "docker-compose.yml")
        (compose_root / ".env").touch()
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            cwd=compose_root,
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


def test_email_worker_has_required_dependencies():
    compose = _load_compose_config()
    worker = compose["services"]["email-worker"]

    assert "app.workers.email_worker.WorkerSettings" in str(worker["command"])
    assert set(worker["depends_on"]) >= {"mysql", "redis"}
    assert "ws" in worker["networks"]
    assert worker["environment"]["DB_HOST"] == "mysql"
    assert worker["environment"]["REDIS_HOST"] == "redis"
    assert worker["environment"]["TZ"] == "Asia/Seoul"


def test_fastapi_uses_mysql_and_redis_services_inside_compose_network():
    compose = _load_compose_config()
    environment = compose["services"]["fastapi"]["environment"]

    assert environment["DB_HOST"] == "mysql"
    assert environment["REDIS_HOST"] == "redis"
    assert environment["REDIS_PORT"] == "6379"
    assert environment["REDIS_DB"] == "0"
