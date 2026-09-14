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
def test_api_hosts_ocr_and_private_volatile_store_without_extra_containers(compose_path: Path):
    compose = _load_compose_config(compose_path)
    fastapi = compose["services"]["fastapi"]
    assert "ocr-worker" not in compose["services"]
    assert "ocr-images" not in compose["services"]
    assert "app.runtime.combined" in str(fastapi["command"])
    assert "/app/.venv/bin/python" in str(fastapi["command"])
    assert set(fastapi["depends_on"]) >= {"mysql", "redis", "qdrant"}
    assert fastapi["environment"]["DB_HOST"] == "mysql"
    assert fastapi["environment"]["REDIS_HOST"] == "redis"
    assert fastapi["environment"]["REDIS_PORT"] == "6379"
    assert fastapi["environment"]["OCR_MAX_JOBS"] == "1"
    assert fastapi["environment"]["TZ"] == "Asia/Seoul"
    assert _has_media_volume(fastapi)
    assert fastapi["memswap_limit"] == fastapi["mem_limit"]
    # Compose's JSON encoder omits zero-valued soft/hard fields.
    assert fastapi["ulimits"]["core"].get("hard", 0) == 0
    assert fastapi["ulimits"]["core"].get("soft", 0) == 0
    assert fastapi["environment"]["OCR_IMAGE_REDIS_URL"] == "redis://127.0.0.1:6380/0"
    assert any(entry.startswith("/run/ocr-images:") for entry in fastapi["tmpfs"])
    assert all(port["target"] != 6380 for port in fastapi.get("ports", []))
    assert "app.runtime.healthcheck" in str(fastapi["healthcheck"]["test"])
    assert fastapi["stop_grace_period"] == "2m0s"
    assert "ocr-private" not in compose.get("networks", {})


@pytest.mark.parametrize("jobs", [0, 3])
def test_ocr_concurrency_rejects_unbounded_or_disabled_execution(jobs: int) -> None:
    with pytest.raises(ValidationError):
        Config(_env_file=None, OCR_MAX_JOBS=jobs)


def test_ocr_defaults_use_one_job_and_loopback_image_store() -> None:
    settings = Config(_env_file=None)
    assert settings.OCR_MAX_JOBS == 1
    assert settings.OCR_IMAGE_REDIS_URL == "redis://127.0.0.1:6380/0"


@pytest.mark.parametrize("ttl_minutes", [0, 61])
def test_ocr_review_ttl_rejects_values_outside_privacy_bound(ttl_minutes: int) -> None:
    with pytest.raises(ValidationError):
        Config(_env_file=None, OCR_REVIEW_TTL_MINUTES=ttl_minutes)

    assert Config(_env_file=None, OCR_REVIEW_TTL_MINUTES=60).OCR_REVIEW_TTL_MINUTES == 60
