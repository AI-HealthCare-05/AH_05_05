from ai_worker.core import (
    Config,
    setup_logger,
)


def test_core_package_uses_ai_worker_dependencies() -> None:
    assert Config.__module__ == ("ai_worker.core.config")
    assert setup_logger.__module__ == ("ai_worker.core.logger")


def test_config_reads_openai_chat_integration_settings(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "OPENAI_CHAT_MODEL",
        "gpt-4o",
    )
    monkeypatch.setenv(
        "RUN_OPENAI_INTEGRATION_TESTS",
        "1",
    )

    settings = Config(
        _env_file=None,
    )

    assert settings.OPENAI_API_KEY is not None
    assert settings.OPENAI_API_KEY.get_secret_value() == "test-api-key"
    assert settings.OPENAI_CHAT_MODEL == "gpt-4o"
    assert settings.RUN_OPENAI_INTEGRATION_TESTS is True
