import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core.db.databases import initialize_tortoise

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)

app.include_router(v1_routers)

if os.environ.get("ENV") != "production":
    from app.dev_push import router as dev_push_router

    app.include_router(dev_push_router)

# 주의: StaticFiles mount("/")는 그 뒤에 등록된 라우터보다 먼저 모든 경로를 가로챈다.
# 그래서 dev_push_router는 반드시 이 mount 앞에 등록해야 한다 — 뒤에 두면
# /dev/push/* 요청이 전부 이 정적 파일 마운트로 먼저 매칭돼 dev_push_router가 죽은 코드가 된다.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
