from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from urllib.request import Request, urlopen

SUPERVISORCTL = "/usr/bin/supervisorctl"
SUPERVISOR_CONFIG = "/app/app/runtime/supervisord.conf"
EXPECTED_PROGRAMS = frozenset({"fatal-guard", "image-redis", "ocr-worker", "api"})
DEFAULT_IMAGE_REDIS_URL = "redis://127.0.0.1:6380/0"
DEFAULT_API_URL = "http://127.0.0.1:8000/api/openapi.json"
DEFAULT_TIMEOUT_SECONDS = 2.0


class HealthcheckError(RuntimeError):
    """Raised when a required process or local dependency is unhealthy."""


def _timeout_seconds() -> float:
    value = float(os.getenv("COMBINED_HEALTHCHECK_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    if value <= 0:
        raise HealthcheckError("healthcheck timeout must be positive")
    return value


def require_running_programs(status_output: str) -> None:
    states: dict[str, str] = {}
    for line in status_output.splitlines():
        columns = line.split()
        if len(columns) >= 2:
            states[columns[0].split(":", 1)[0]] = columns[1]
    unhealthy = sorted(name for name in EXPECTED_PROGRAMS if states.get(name) != "RUNNING")
    if unhealthy:
        raise HealthcheckError(f"supervisor program is not RUNNING: {', '.join(unhealthy)}")


def check_supervisor() -> None:
    try:
        result = subprocess.run(
            [SUPERVISORCTL, "-c", SUPERVISOR_CONFIG, "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_timeout_seconds(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise HealthcheckError("supervisor status check failed") from error
    if result.returncode != 0:
        raise HealthcheckError("supervisor status check failed")
    require_running_programs(result.stdout)


def check_image_redis() -> None:
    from redis import Redis
    from redis.exceptions import RedisError

    timeout = _timeout_seconds()
    client = Redis.from_url(
        os.getenv("OCR_IMAGE_REDIS_URL", DEFAULT_IMAGE_REDIS_URL),
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    try:
        if not client.ping():
            raise HealthcheckError("image Redis did not respond")
    except (OSError, RedisError) as error:
        raise HealthcheckError("image Redis check failed") from error
    finally:
        client.close()


def check_worker_heartbeat() -> None:
    from redis import Redis
    from redis.exceptions import RedisError

    timeout = _timeout_seconds()
    client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    key = f"{os.getenv('OCR_QUEUE_NAME', 'arq:ocr')}:health-check"
    try:
        if not client.exists(key):
            raise HealthcheckError("OCR worker heartbeat is missing")
    except (OSError, RedisError) as error:
        raise HealthcheckError("OCR worker heartbeat check failed") from error
    finally:
        client.close()


def check_api() -> None:
    request = Request(os.getenv("COMBINED_API_HEALTH_URL", DEFAULT_API_URL), method="GET")
    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:  # noqa: S310
            if response.status != 200:
                raise HealthcheckError("API readiness endpoint returned a non-200 status")
    except HealthcheckError:
        raise
    except OSError as error:
        raise HealthcheckError("API readiness check failed") from error


def run_checks(
    *,
    supervisor_check: Callable[[], None] = check_supervisor,
    image_redis_check: Callable[[], None] = check_image_redis,
    worker_heartbeat_check: Callable[[], None] = check_worker_heartbeat,
    api_check: Callable[[], None] = check_api,
) -> None:
    supervisor_check()
    image_redis_check()
    worker_heartbeat_check()
    api_check()


def main() -> int:
    try:
        run_checks()
    except (HealthcheckError, ValueError):
        print("combined runtime healthcheck failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
