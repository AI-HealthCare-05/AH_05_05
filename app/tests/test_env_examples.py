"""envs/example.*.env 의 메일 설정을 고정한다 (#137).

example.prod.env 가 console 이면 배포 시 메일이 나가지 않고 임시 비밀번호와 수신자
PII 가 운영 로그에 평문으로 남는다. Config 기본값도 console 이라 값을 지우는 것으로도
같은 사고가 나므로, 이 예시 파일이 사실상 유일한 방어선이다. 누가 되돌리면 CI 가 잡는다.
"""

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
    def test_does_not_use_console_email_backend(self) -> None:
        backend = read_env(EXAMPLE_PROD_ENV)["EMAIL_BACKEND"]

        assert backend != "console", (
            "운영에서 console 을 쓰면 메일이 발송되지 않고 임시 비밀번호가 평문으로 로그에 남는다"
        )
        assert backend == "smtp"

    def test_keeps_smtp_password_empty(self) -> None:
        """예시 파일에 시크릿을 두지 않는다. 배포 시 주입한다."""
        assert read_env(EXAMPLE_PROD_ENV)["SMTP_PASSWORD"] == ""


class TestExampleLocalEnv:
    def test_keeps_console_email_backend(self) -> None:
        """로컬은 console 이 맞다. 실제 발송 없이 메일 내용을 확인하기 위함이다."""
        assert read_env(EXAMPLE_LOCAL_ENV)["EMAIL_BACKEND"] == "console"
