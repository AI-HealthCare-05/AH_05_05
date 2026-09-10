from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_runs_a_dedicated_custom_challenge_worker() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    worker = compose["services"].get("custom-challenge-worker")

    assert worker is not None
    assert worker["command"] == "uv run --no-sync arq app.workers.custom_challenge_worker.WorkerSettings"
    assert worker["environment"]["TZ"] == "Asia/Seoul"
    assert worker["depends_on"]["mysql"]["condition"] == "service_healthy"
    assert worker["depends_on"]["redis"]["condition"] == "service_healthy"
