"""envs/example.*.env 의 전용 email-worker 설정을 고정한다."""

from pathlib import Path

ENVS_DIR = Path(__file__).resolve().parents[2] / "envs"
EXAMPLE_PROD_ENV = ENVS_DIR / "example.prod.env"
EXAMPLE_LOCAL_ENV = ENVS_DIR / "example.local.env"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


class TestExampleProdEnv:
    def test_configures_dedicated_email_worker_queue_and_retry(self) -> None:
        values = read_env(EXAMPLE_PROD_ENV)

        assert values["EMAIL_QUEUE_NAME"] == "arq:email"
        assert values["EMAIL_MAX_RETRY_COUNT"] == "3"
        assert values["EMAIL_RETRY_BASE_SECONDS"] == "30"
        assert "EMAIL_BACKEND" not in values

    def test_keeps_smtp_password_empty(self) -> None:
        """예시 파일에 시크릿을 두지 않는다. 배포 시 주입한다."""
        values = read_env(EXAMPLE_PROD_ENV)

        assert values["SMTP_PASSWORD"] == ""
        assert values["EMAIL_PAYLOAD_ENCRYPTION_KEY"] == ""
        assert values["SMTP_SETTINGS_ENCRYPTION_KEY"] == ""
        assert values["SMTP_FROM_EMAIL"] == "replace-with-smtp-account@example.com"
        assert "SMTP_FROM" not in values


class TestExampleLocalEnv:
    def test_uses_same_dedicated_queue_contract_without_console_backend(self) -> None:
        values = read_env(EXAMPLE_LOCAL_ENV)

        assert values["EMAIL_QUEUE_NAME"] == "arq:email"
        assert values["EMAIL_MAX_RETRY_COUNT"] == "3"
        assert values["EMAIL_RETRY_BASE_SECONDS"] == "30"
        assert values["EMAIL_PAYLOAD_ENCRYPTION_KEY"] == ""
        assert values["SMTP_SETTINGS_ENCRYPTION_KEY"] == ""
        assert values["SMTP_FROM_EMAIL"] == ""
        assert "SMTP_FROM" not in values
        assert "EMAIL_BACKEND" not in values
