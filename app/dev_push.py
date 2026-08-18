"""웹푸시 최소 검증용. 검증이 끝나면 이 파일을 삭제하고 정식 구조로 옮깁니다.

- 인증 없음 · DB 없음(메모리 리스트). 서버를 재시작하면 구독이 사라집니다.
- pywebpush 는 동기 라이브러리라 이벤트 루프를 막습니다. 구독 1~2건 검증에는 문제없지만
  정식 구현에서는 asyncio.to_thread 로 감싸야 합니다.
"""

import json
import os

from fastapi import APIRouter, Response
from pydantic import BaseModel
from pywebpush import WebPushException, webpush

router = APIRouter(prefix="/dev/push", tags=["dev"])

_subs: list[dict] = []


class Keys(BaseModel):
    p256dh: str
    auth: str


class Sub(BaseModel):
    endpoint: str
    keys: Keys


@router.post("/subscribe", status_code=204)
async def subscribe(sub: Sub) -> Response:
    info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.keys.p256dh, "auth": sub.keys.auth}}
    if info not in _subs:
        _subs.append(info)
    print(f"[push] 구독 {len(_subs)}건 · {sub.endpoint[:60]}...")
    return Response(status_code=204)


@router.post("/send")
async def send() -> dict:
    payload = json.dumps(
        {
            "title": "약 드실 시간입니다",
            "body": "아침 08:00 · 셀레콕시브, 파모티딘",
            "url": "/",
        },
        ensure_ascii=False,
    )
    sent = 0
    failed = []
    for info in list(_subs):
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:dev@example.com")},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            failed.append({"status": status, "detail": str(exc)[:200]})
            if status in (404, 410):
                _subs.remove(info)  # 죽은 구독
    return {"subscriptions": len(_subs), "sent": sent, "failed": failed}
