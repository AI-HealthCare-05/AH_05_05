import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError

from app.core.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _has_media_volume(service: dict) -> bool:
    return any(
        volume["type"] == "volume" and volume["source"] == "media_volume" and volume["target"] == "/app/media"
        for volume in service.get("volumes", [])
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
def test_ocr_worker_uses_volatile_image_store_and_required_dependencies(compose_path: Path):
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
    assert not _has_media_volume(worker)
    assert _has_media_volume(fastapi)
    volatile = compose["services"]["ocr-images"]
    assert volatile.get("ports", []) == []
    assert volatile.get("volumes", []) == []
    assert volatile["read_only"] is True
    assert volatile["memswap_limit"] == volatile["mem_limit"]
    command = volatile["command"]
    assert command[command.index("--save") + 1] == ""
    assert command[command.index("--appendonly") + 1] == "no"
    assert command[command.index("--maxmemory-policy") + 1] == "noeviction"
    assert "ocr-images" in worker["depends_on"]
    assert "ocr-images" in fastapi["depends_on"]
    assert worker["environment"]["OCR_IMAGE_REDIS_URL"] == "redis://ocr-images:6379/0"
    assert fastapi["environment"]["OCR_IMAGE_REDIS_URL"] == "redis://ocr-images:6379/0"
    assert compose["networks"]["ocr-private"]["internal"] is True
    assert set(volatile["networks"]) == {"ocr-private"}
    assert {"ws", "ocr-private"} <= set(worker["networks"])
    assert {"ws", "ocr-private"} <= set(fastapi["networks"])
    private_members = {
        service_name
        for service_name, service in compose["services"].items()
        if "ocr-private" in service.get("networks", [])
    }
    assert private_members == {"ocr-images", "fastapi", "ocr-worker"}


@pytest.mark.parametrize("ttl_minutes", [0, 61])
def test_ocr_review_ttl_rejects_values_outside_privacy_bound(ttl_minutes: int) -> None:
    with pytest.raises(ValidationError):
        Config(_env_file=None, OCR_REVIEW_TTL_MINUTES=ttl_minutes)

    assert Config(_env_file=None, OCR_REVIEW_TTL_MINUTES=60).OCR_REVIEW_TTL_MINUTES == 60
