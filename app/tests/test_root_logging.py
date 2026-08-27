"""root 로거가 INFO 를 버려 콘솔 메일 로그가 사라지던 문제의 회귀 테스트 (#137).

여기서는 ``caplog.at_level`` / ``caplog.set_level`` 을 쓰지 않는다. 레벨을 강제하는
순간 root 전파 여부와 무관하게 통과해 버려, 정작 이 버그를 못 잡는 테스트가 된다.
(``app/tests/admin_apis/test_admin_email.py`` 의 ``test_logs_message_body`` 가 그 예다.)
caplog 는 root 에 핸들러만 붙이므로, 레벨을 건드리지 않으면 실운영 경로가 그대로 재현된다.
"""

import logging

import pytest
from _pytest.logging import LogCaptureFixture
from _pytest.monkeypatch import MonkeyPatch

# 임포트 자체가 검증 대상이다. app/main.py 가 모듈 로드 시 configure_root_logging 을 부른다.
import app.main  # noqa: F401
from app.core.email.backends import CONSOLE_BACKEND_WARNING, ConsoleEmailBackend, EmailMessage

BACKENDS_LOGGER_NAME = "app.core.email.backends"


def test_backends_logger_effective_level_allows_info() -> None:
    """앱을 임포트하면 메일 백엔드 로거가 INFO 를 통과시켜야 한다."""
    effective_level = logging.getLogger(BACKENDS_LOGGER_NAME).getEffectiveLevel()

    assert effective_level <= logging.INFO, (
        f"effective level 이 {logging.getLevelName(effective_level)} 이라 logger.info 가 버려진다"
    )


def test_root_logger_has_handler() -> None:
    """레벨만 낮추고 핸들러가 없으면 아무 데도 출력되지 않는다."""
    assert logging.getLogger().handlers


class TestConsoleEmailBackendLogging:
    @pytest.fixture(autouse=True)
    def reset_warning_state(self, monkeypatch: MonkeyPatch) -> None:
        # 클래스 플래그라 테스트 간에 새므로 매번 되돌린다.
        monkeypatch.setattr(ConsoleEmailBackend, "_warned", False)

    def test_logs_body_without_touching_levels(self, caplog: LogCaptureFixture) -> None:
        """실운영 경로 재현. 레벨을 조작하지 않고 앱 설정 그대로 호출한다."""
        message = EmailMessage(to="jisu@ozcoding.ai", subject="제목", body="임시 비밀번호 : Temp1234!")

        ConsoleEmailBackend().send(message)

        text = caplog.text
        assert "[console email]" in text
        assert "jisu@ozcoding.ai" in text
        assert "Temp1234!" in text

    def test_warns_that_plaintext_is_logged(self, caplog: LogCaptureFixture) -> None:
        ConsoleEmailBackend().send(EmailMessage(to="jisu@ozcoding.ai", subject="제목", body="본문"))

        warnings = [
            record
            for record in caplog.records
            if record.name == BACKENDS_LOGGER_NAME and record.levelno == logging.WARNING
        ]
        assert [record.getMessage() for record in warnings] == [CONSOLE_BACKEND_WARNING]

    def test_warns_only_once(self, caplog: LogCaptureFixture) -> None:
        """매 발송마다 찍으면 시끄러워서 아무도 안 읽는다."""
        backend = ConsoleEmailBackend()
        message = EmailMessage(to="jisu@ozcoding.ai", subject="제목", body="본문")

        backend.send(message)
        backend.send(message)
        backend.send(message)

        warning_count = sum(
            1 for record in caplog.records if record.name == BACKENDS_LOGGER_NAME and record.levelno == logging.WARNING
        )
        assert warning_count == 1
