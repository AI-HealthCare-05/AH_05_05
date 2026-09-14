from __future__ import annotations

import os
import signal
import sys
from collections.abc import Callable
from typing import TextIO


def _header_fields(header: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in header.split():
        key, separator, value = item.partition(":")
        if separator:
            fields[key] = value
    return fields


def _process_name(payload: str) -> str:
    for item in payload.split():
        key, separator, value = item.partition(":")
        if separator and key == "processname":
            return value
    return "unknown"


def handle_one_event(
    *,
    source: TextIO,
    sink: TextIO,
    supervisor_pid: int,
    terminate: Callable[[int, signal.Signals], object] = os.kill,
) -> None:
    sink.write("READY\n")
    sink.flush()
    header = source.readline()
    if not header:
        raise EOFError("supervisor event stream closed")
    fields = _header_fields(header)
    length = int(fields.get("len", "0"))
    payload = source.read(length)
    sink.write("RESULT 2\nOK")
    sink.flush()
    if fields.get("eventname") == "PROCESS_STATE_FATAL":
        print(
            f"combined runtime process entered FATAL state: {_process_name(payload)}",
            file=sys.stderr,
            flush=True,
        )
        terminate(supervisor_pid, signal.SIGTERM)


def main() -> int:
    while True:
        handle_one_event(
            source=sys.stdin,
            sink=sys.stdout,
            supervisor_pid=os.getppid(),
        )


if __name__ == "__main__":
    raise SystemExit(main())
