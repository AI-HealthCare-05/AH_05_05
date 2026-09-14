from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_local_compose_runs_alarm_tasks_in_fastapi_without_alarm_worker() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    services = compose["services"]
    assert "fastapi" in services
    assert "alarm-worker" not in services
    assert "app.workers.alarm_worker" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_production_compose_runs_alarm_tasks_in_fastapi_without_alarm_worker() -> None:
    path = ROOT / "infra/docker/docker-compose.prod.yml"
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))

    services = compose["services"]
    assert "fastapi" in services
    assert "alarm-worker" not in services
    assert "app.workers.alarm_worker" not in path.read_text(encoding="utf-8")
