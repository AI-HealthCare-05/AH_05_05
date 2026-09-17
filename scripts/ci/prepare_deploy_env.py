"""Prepare a private deployment env file from stdin; never print its contents."""

import os
import re
import sys
from datetime import datetime
from pathlib import Path


def main():
    if len(sys.argv) != 5:
        raise SystemExit("Usage: prepare_deploy_env.py OUTPUT APP_VERSION AI_VERSION DOCKER_USER")
    output, app, ai, user = sys.argv[1:]
    version_pattern = r"build-[0-9]{8}-[1-9][0-9]*"
    if any(not re.fullmatch(version_pattern, value) or len(value) > 100 for value in (app, ai)):
        raise SystemExit("Versions must be build-YYYYMMDD-N with a positive sequence")
    try:
        for value in (app, ai):
            datetime.strptime(value.split("-")[1], "%Y%m%d")
    except ValueError:
        raise SystemExit("Build version contains an invalid calendar date") from None
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,38}", user):
        raise SystemExit("Invalid Docker Hub username")
    source = sys.stdin.read().replace("\r\n", "\n")
    if not source.strip() or "\x00" in source:
        raise SystemExit("PROD_ENV_FILE is empty or invalid")
    settings = {
        "APP_VERSION": app,
        "AI_WORKER_VERSION": ai,
        "DOCKER_USER": user,
        "DOCKER_REPOSITORY": "rxvita",
    }
    for key, value in settings.items():
        pattern = rf"(?m)^[ \t]*(?:export[ \t]+)?{key}[ \t]*=.*$"
        matches = re.findall(pattern, source)
        if len(matches) > 1:
            raise SystemExit(f"Duplicate deployment setting: {key}")
        if matches:
            source = re.sub(pattern, f"{key}={value}", source)
        else:
            source = source.rstrip("\n") + f"\n{key}={value}\n"
    # Refuse overwrite/symlinks and create restrictive permissions from the start.
    descriptor = os.open(Path(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(source.rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
