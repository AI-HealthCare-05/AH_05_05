import logging
from io import StringIO

import app.core.logger as logger_module
from app.core.logger import configure_db_query_logging


def test_db_query_logging_is_disabled_at_warning_level():
    logger = configure_db_query_logging(enabled=False)

    assert logger.level == logging.WARNING


def test_db_query_logging_writes_redacted_query_to_stdout(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(logger_module.sys, "stdout", output)
    logger = configure_db_query_logging(enabled=True)

    logger.debug("%s: %s", "SELECT * FROM users WHERE email=%s", ["secret@example.com"])

    log_output = output.getvalue()
    assert "SELECT * FROM users WHERE email=%s" in log_output
    assert "<redacted>" in log_output
    assert "secret@example.com" not in log_output
