import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
            [
                "docker",
                "compose",
                "-f",
                str(local_compose),
                "config",
                "--format",
                "json",
            ],
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
    [
        PROJECT_ROOT / "docker-compose.yml",
        PROJECT_ROOT / "infra/docker/docker-compose.prod.yml",
    ],
)
def test_fastapi_chat_runtime_can_reach_qdrant(
    compose_path: Path,
) -> None:
    compose = _load_compose_config(compose_path)
    fastapi = compose["services"]["fastapi"]

    assert "qdrant" in compose["services"]
    assert fastapi["environment"]["QDRANT_URL"] == ("http://qdrant:6333")
    assert "qdrant" in fastapi["depends_on"]


def test_fastapi_image_contains_minimum_chat_core_runtime() -> None:
    dockerfile = (PROJECT_ROOT / "app/Dockerfile").read_text(encoding="utf-8")
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    app_dependencies = pyproject["dependency-groups"]["app"]

    assert "COPY ./ai_worker ./ai_worker" in dockerfile
    assert any(dependency.startswith("qdrant-client") for dependency in app_dependencies)
    assert any(dependency.startswith("langchain-openai") for dependency in app_dependencies)
