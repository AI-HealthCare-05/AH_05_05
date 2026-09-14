from pathlib import Path

import pytest
import yaml

from app.core.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "compose_path",
    [PROJECT_ROOT / "docker-compose.yml", PROJECT_ROOT / "infra/docker/docker-compose.prod.yml"],
)
def test_compose_runs_email_tasks_in_fastapi_without_email_worker(compose_path: Path) -> None:
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    assert "fastapi" in compose["services"]
    assert "email-worker" not in compose["services"]


def test_config_does_not_expose_an_email_queue_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_QUEUE_NAME", "arq:email")

    config = Config(_env_file=None)

    assert not hasattr(config, "EMAIL_QUEUE_NAME")
    assert "EMAIL_QUEUE_NAME" not in Config.model_fields
