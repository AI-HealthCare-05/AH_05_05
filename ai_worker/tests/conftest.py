import sqlite3
from datetime import time


def _adapt_local_time(value: time) -> str:
    return value.replace(tzinfo=None).isoformat()


# SQLite는 datetime.time을 기본 지원하지 않습니다. 운영 DB의 TimeField와
# 동일한 현지 시각 의미를 유지하도록 AI Worker 단위 테스트에서만 변환합니다.
sqlite3.register_adapter(time, _adapt_local_time)
