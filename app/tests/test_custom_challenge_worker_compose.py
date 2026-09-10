from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_keeps_api_and_other_workers_without_a_challenge_scheduler() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    services = compose["services"]
    assert "custom-challenge-worker" not in services
    assert {"fastapi", "mysql", "redis", "alarm-worker", "ocr-worker", "email-worker", "ai-worker"} <= services.keys()
