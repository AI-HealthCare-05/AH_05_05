import logging
import sys


class _QueryParameterRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg == "%s: %s" and isinstance(record.args, tuple) and len(record.args) == 2:
            record.args = (record.args[0], "<redacted>")
        return True


class _DbQueryConsoleHandler(logging.StreamHandler):
    pass


def configure_db_query_logging(enabled: bool) -> logging.Logger:
    query_logger = logging.getLogger("tortoise.db_client")
    query_logger.setLevel(logging.DEBUG if enabled else logging.WARNING)
    query_logger.propagate = False

    if not any(isinstance(log_filter, _QueryParameterRedactionFilter) for log_filter in query_logger.filters):
        query_logger.addFilter(_QueryParameterRedactionFilter())

    if enabled:
        query_handler = next(
            (handler for handler in query_logger.handlers if isinstance(handler, _DbQueryConsoleHandler)),
            None,
        )
        if query_handler is None:
            query_handler = _DbQueryConsoleHandler(sys.stdout)
            query_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
            query_logger.addHandler(query_handler)
        else:
            query_handler.setStream(sys.stdout)

    return query_logger


def setup_logger(
    name: str = "ai_worker",
    level: int = logging.INFO,
) -> logging.Logger:
    _logger = logging.getLogger(name)

    # 중복 핸들러 방지 (중요)
    if _logger.handlers:
        return _logger

    _logger.setLevel(level)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")

    # 콘솔 출력
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    _logger.addHandler(console_handler)
    _logger.propagate = False  # root logger로 중복 전달 방지

    return _logger


# 앱 전역에서 사용할 로거
default_logger = setup_logger()
