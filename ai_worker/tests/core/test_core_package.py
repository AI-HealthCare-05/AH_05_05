from ai_worker.core import (
    Config,
    setup_logger,
)


def test_core_package_uses_ai_worker_dependencies() -> None:
    assert Config.__module__ == (
        "ai_worker.core.config"
    )
    assert setup_logger.__module__ == (
        "ai_worker.core.logger"
    )
