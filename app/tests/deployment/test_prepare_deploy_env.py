import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/ci/prepare_deploy_env.py"


def run_prepare(tmp_path, source, app="build-20260917-1", ai="build-20260917-1"):
    assert SCRIPT.is_file(), "Deployment environment preparation is not implemented"
    output = tmp_path / "production.env"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(output), app, ai, "blesseunmi82"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output


def test_replaces_image_versions_without_disclosing_or_changing_secrets(tmp_path):
    result, output = run_prepare(
        tmp_path,
        '# production\nDB_PASSWORD="secret=$value#keep"\nAPP_VERSION=v0.1.0\n'
        "AI_WORKER_VERSION=v0.1.0\nDOCKER_USER=old\nDOCKER_REPOSITORY=old\n",
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == (
        '# production\nDB_PASSWORD="secret=$value#keep"\n'
        "APP_VERSION=build-20260917-1\nAI_WORKER_VERSION=build-20260917-1\n"
        "DOCKER_USER=blesseunmi82\nDOCKER_REPOSITORY=rxvita\n"
    )
    assert "secret=" not in result.stdout + result.stderr
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_missing_image_settings_are_added(tmp_path):
    result, output = run_prepare(tmp_path, "DB_HOST=mysql\n")
    assert result.returncode == 0, result.stderr
    assert "APP_VERSION=build-20260917-1\n" in output.read_text()
    assert "AI_WORKER_VERSION=build-20260917-1\n" in output.read_text()


def test_rejects_shell_input_before_creating_file(tmp_path):
    result, output = run_prepare(tmp_path, "DB_HOST=mysql\n", app="build-20260917-1;id")
    assert result.returncode != 0
    assert not output.exists()


def test_rejects_duplicate_settings_and_empty_secret(tmp_path):
    for source in ("", "APP_VERSION=v1.0.0\nexport APP_VERSION=v2.0.0\n"):
        result, output = run_prepare(tmp_path, source)
        assert result.returncode != 0
        assert not output.exists()


def test_rejects_invalid_date_or_zero_sequence(tmp_path):
    for version in ("build-20260230-1", "build-20260917-0", "build-20260917-01", "v1.0.2"):
        result, output = run_prepare(tmp_path, "DB_HOST=mysql\n", app=version)
        assert result.returncode != 0
        assert not output.exists()
