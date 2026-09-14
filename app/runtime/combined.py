from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import NoReturn

SUPERVISORD = "/usr/bin/supervisord"
SUPERVISOR_CONFIG = "/app/app/runtime/supervisord.conf"
DEFAULT_IMAGE_REDIS_URL = "redis://127.0.0.1:6380/0"
DEFAULT_STARTUP_TIMEOUT_SECONDS = 5.0


class StartupDependencyError(RuntimeError):
    """Raised when a local runtime dependency never becomes ready."""


def _image_redis_ping() -> bool:
    from redis import Redis
    from redis.exceptions import RedisError

    client = Redis.from_url(
        os.getenv("OCR_IMAGE_REDIS_URL", DEFAULT_IMAGE_REDIS_URL),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        return bool(client.ping())
    except (OSError, RedisError):
        return False
    finally:
        client.close()


def wait_for_image_redis(
    *,
    timeout_seconds: float,
    probe: Callable[[], bool] = _image_redis_ping,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    deadline = monotonic() + timeout_seconds
    while not probe():
        if monotonic() >= deadline:
            raise StartupDependencyError("image Redis did not become ready before the startup deadline")
        sleep(0.2)


def run_gated(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    probe: Callable[[], bool] = _image_redis_ping,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    exec_fn: Callable[[str, Sequence[str]], object] = os.execv,
) -> None:
    if not command or not command[0].startswith("/"):
        raise ValueError("the gated command must use an absolute executable path")
    wait_for_image_redis(
        timeout_seconds=timeout_seconds,
        probe=probe,
        sleep=sleep,
        monotonic=monotonic,
    )
    exec_fn(command[0], command)


def launch_supervisord(
    *,
    exec_fn: Callable[[str, Sequence[str]], object] = os.execv,
) -> None:
    argv = (SUPERVISORD, "-n", "-c", SUPERVISOR_CONFIG)
    exec_fn(SUPERVISORD, argv)


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _startup_timeout() -> float:
    return _positive_float(os.getenv("COMBINED_STARTUP_TIMEOUT_SECONDS", str(DEFAULT_STARTUP_TIMEOUT_SECONDS)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the combined API and OCR process supervisor")
    subparsers = parser.add_subparsers(dest="action")
    gate = subparsers.add_parser("gate", help="wait for the private image Redis before exec")
    gate.add_argument("--timeout", type=_positive_float, default=None)
    gate.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int | NoReturn:
    args = _parser().parse_args(argv)
    if args.action is None:
        launch_supervisord()
        return 0

    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    try:
        run_gated(command, timeout_seconds=args.timeout or _startup_timeout())
    except StartupDependencyError as error:
        print(f"combined runtime startup failed: {error}", file=sys.stderr)
        return 70
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
