import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _has_media_volume(service: dict) -> bool:
    return any(
        volume["type"] == "volume" and volume["source"] == "media_volume" and volume["target"] == "/app/media"
        for volume in service["volumes"]
    )


def _load_compose_config(compose_path: Path) -> dict:
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
        local_compose = compose_root / "docker-compose.yml"
        shutil.copy2(compose_path, local_compose)
        (compose_root / ".env").touch()
        result = subprocess.run(
            ["docker", "compose", "-f", str(local_compose), "config", "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            cwd=compose_root,
            env=compose_env,
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "compose_path",
    [PROJECT_ROOT / "docker-compose.yml", PROJECT_ROOT / "infra/docker/docker-compose.prod.yml"],
)
def test_ocr_worker_uses_shared_media_volume_and_required_dependencies(compose_path: Path):
    compose = _load_compose_config(compose_path)
    worker = compose["services"]["ocr-worker"]
    fastapi = compose["services"]["fastapi"]

    assert "app.workers.medication_guide_ocr_worker.WorkerSettings" in str(worker["command"])
    assert set(worker["depends_on"]) >= {"mysql", "redis"}
    assert worker["environment"]["DB_HOST"] == "mysql"
    assert worker["environment"]["REDIS_HOST"] == "redis"
    assert fastapi["environment"]["REDIS_HOST"] == "redis"
    assert fastapi["environment"]["REDIS_PORT"] == "6379"
    assert worker["environment"]["TZ"] == "Asia/Seoul"
    assert _has_media_volume(worker)
    assert _has_media_volume(fastapi)
