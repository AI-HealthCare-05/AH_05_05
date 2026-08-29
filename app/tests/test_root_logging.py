"""애플리케이션 root 로깅 설정 회귀 테스트."""

import logging

# 임포트 자체가 검증 대상이다. app/main.py 가 모듈 로드 시 configure_root_logging 을 부른다.
import app.main  # noqa: F401


def test_root_logger_has_handler() -> None:
    """레벨만 낮추고 핸들러가 없으면 아무 데도 출력되지 않는다."""
    assert logging.getLogger().handlers
