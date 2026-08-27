import logging
import sys

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"


class _QueryParameterRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg == "%s: %s" and isinstance(record.args, tuple) and len(record.args) == 2:
            record.args = (record.args[0], "<redacted>")
        return True


class _DbQueryConsoleHandler(logging.StreamHandler):
    pass


class _RootConsoleHandler(logging.StreamHandler):
    """root 에 우리가 붙인 핸들러임을 표시한다. 재호출 시 중복 부착을 막는 용도."""


def configure_root_logging(level: int | str = logging.INFO) -> logging.Logger:
    """root 로거에 콘솔 핸들러와 레벨을 붙인다.

    uvicorn 은 uvicorn* 로거만 설정하고 root 는 손대지 않는다. root 가 기본 WARNING 이라
    이 함수 없이는 앱 코드의 ``logger.info`` 가 전부 조용히 사라진다.
    (``--log-level info`` 도 uvicorn 로거용이라 소용이 없다.)

    dictConfig 를 쓰지 않는 이유는 ``disable_existing_loggers`` 로 이미 설정된 로거
    (uvicorn, tortoise.db_client)를 죽이지 않기 위해서다.

    uvicorn 로거는 ``propagate = False`` 라 root 까지 올라오지 않으므로 중복 출력은 없다.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    root_handler = next(
        (handler for handler in root_logger.handlers if isinstance(handler, _RootConsoleHandler)),
        None,
    )
    if root_handler is None:
        root_handler = _RootConsoleHandler(sys.stdout)
        root_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(root_handler)
    else:
        root_handler.setStream(sys.stdout)

    return root_logger


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
            query_handler.setFormatter(logging.Formatter(LOG_FORMAT))
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

    formatter = logging.Formatter(LOG_FORMAT)

    # 콘솔 출력
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    _logger.addHandler(console_handler)
    _logger.propagate = False  # root logger로 중복 전달 방지

    return _logger


# 앱 전역에서 사용할 로거
default_logger = setup_logger()
