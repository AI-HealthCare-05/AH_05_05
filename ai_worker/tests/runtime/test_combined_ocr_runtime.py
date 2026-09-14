from __future__ import annotations

import configparser
import io
import signal
from pathlib import Path

import pytest

from app.runtime import combined, fatal_guard, healthcheck

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUPERVISOR_CONFIG = PROJECT_ROOT / "app" / "runtime" / "supervisord.conf"


def _supervisor_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    with SUPERVISOR_CONFIG.open(encoding="utf-8") as config_file:
        parser.read_file(config_file)
    return parser


def test_launcher_replaces_itself_with_supervisord() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    combined.launch_supervisord(exec_fn=lambda executable, argv: calls.append((executable, tuple(argv))))

    assert calls == [
        (
            "/usr/bin/supervisord",
            ("/usr/bin/supervisord", "-n", "-c", "/app/app/runtime/supervisord.conf"),
        )
    ]


def test_redis_gate_retries_then_executes_child_without_a_shell() -> None:
    probes = iter([False, False, True])
    sleeps: list[float] = []
    calls: list[tuple[str, tuple[str, ...]]] = []

    combined.run_gated(
        ["/app/.venv/bin/python", "-m", "uvicorn"],
        timeout_seconds=5,
        probe=lambda: next(probes),
        sleep=sleeps.append,
        monotonic=iter([0.0, 0.1, 0.2]).__next__,
        exec_fn=lambda executable, argv: calls.append((executable, tuple(argv))),
    )

    assert sleeps == [0.2, 0.2]
    assert calls == [
        (
            "/app/.venv/bin/python",
            ("/app/.venv/bin/python", "-m", "uvicorn"),
        )
    ]


def test_redis_gate_fails_after_a_bounded_timeout_without_echoing_connection_data() -> None:
    with pytest.raises(combined.StartupDependencyError, match="image Redis did not become ready") as error:
        combined.wait_for_image_redis(
            timeout_seconds=1,
            probe=lambda: False,
            sleep=lambda _seconds: None,
            monotonic=iter([0.0, 0.4, 1.0]).__next__,
        )

    assert "redis://" not in str(error.value)


def test_fatal_listener_acknowledges_event_then_terminates_supervisord() -> None:
    payload = "processname:ocr-worker groupname:ocr-worker from_state:BACKOFF"
    source = io.StringIO(f"ver:3.0 eventname:PROCESS_STATE_FATAL len:{len(payload)}\n{payload}")
    sink = io.StringIO()
    signals: list[tuple[int, signal.Signals]] = []

    fatal_guard.handle_one_event(
        source=source,
        sink=sink,
        supervisor_pid=321,
        terminate=lambda pid, sig: signals.append((pid, sig)),
    )

    assert sink.getvalue() == "READY\nRESULT 2\nOK"
    assert signals == [(321, signal.SIGTERM)]


def test_supervisor_config_keeps_image_redis_alive_until_ocr_shutdown_finishes() -> None:
    config = _supervisor_config()
    redis_program = config["program:image-redis"]
    worker_program = config["program:ocr-worker"]
    api_program = config["program:api"]

    assert int(redis_program["priority"]) < int(worker_program["priority"]) < int(api_program["priority"])
    assert redis_program["autorestart"] == "true"
    assert worker_program["autorestart"] == "true"
    assert api_program["autorestart"] == "true"
    assert int(worker_program["stopwaitsecs"]) >= 70
    assert worker_program["stopasgroup"] == "true"
    assert worker_program["killasgroup"] == "true"
    assert api_program["command"].startswith("/app/.venv/bin/python -m app.runtime.combined gate ")
    assert "gate --timeout 5 --" in api_program["command"]
    assert "gate --timeout 5 --" in worker_program["command"]
    assert "--workers 1" in api_program["command"]
    assert "app.workers.medication_guide_ocr_worker.WorkerSettings" in worker_program["command"]


def test_gate_failure_happens_before_supervisor_marks_child_running() -> None:
    config = _supervisor_config()
    shortest_start_window = min(
        int(config["program:ocr-worker"]["startsecs"]),
        int(config["program:api"]["startsecs"]),
    )

    assert 0 < combined.DEFAULT_STARTUP_TIMEOUT_SECONDS < shortest_start_window
    assert healthcheck.DEFAULT_TIMEOUT_SECONDS == 2.0


def test_supervisor_config_uses_nonpersistent_loopback_image_redis_and_fatal_guard() -> None:
    config = _supervisor_config()
    redis_command = config["program:image-redis"]["command"]
    listener = config["eventlistener:fatal-guard"]

    assert redis_command == "/usr/bin/redis-server /app/app/runtime/image-redis.conf"
    assert listener["events"] == "PROCESS_STATE_FATAL"
    assert listener["command"] == "/app/.venv/bin/python -m app.runtime.fatal_guard"


@pytest.mark.parametrize(
    ("status_output", "missing"),
    [
        ("fatal-guard:fatal-guard_00 RUNNING\nimage-redis RUNNING\nocr-worker RUNNING\napi RUNNING\n", None),
        ("fatal-guard RUNNING\nimage-redis RUNNING\nocr-worker FATAL\napi RUNNING\n", "ocr-worker"),
        ("fatal-guard RUNNING\nimage-redis RUNNING\napi RUNNING\n", "ocr-worker"),
        ("image-redis RUNNING\nocr-worker RUNNING\napi RUNNING\n", "fatal-guard"),
    ],
)
def test_supervisor_health_requires_every_runtime_program_running(status_output: str, missing: str | None) -> None:
    if missing is None:
        healthcheck.require_running_programs(status_output)
        return

    with pytest.raises(healthcheck.HealthcheckError, match=missing):
        healthcheck.require_running_programs(status_output)


def test_healthcheck_covers_supervisor_image_store_worker_heartbeat_and_http() -> None:
    checks: list[str] = []

    healthcheck.run_checks(
        supervisor_check=lambda: checks.append("supervisor"),
        image_redis_check=lambda: checks.append("image-redis"),
        worker_heartbeat_check=lambda: checks.append("ocr-heartbeat"),
        api_check=lambda: checks.append("api"),
    )

    assert checks == ["supervisor", "image-redis", "ocr-heartbeat", "api"]
