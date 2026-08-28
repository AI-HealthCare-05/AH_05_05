from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.apis.v1 import v1_routers
from app.core import config
from app.core.api_timeout import ApiTimeoutMiddleware
from app.core.db.databases import initialize_tortoise
from app.core.exception_handlers import register_exception_handlers
from app.core.logger import configure_db_query_logging, configure_root_logging
from app.core.ocr_upload_middleware import OcrUploadSizeLimitMiddleware
from app.core.static_files import NoCacheStaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

# root 먼저. 이걸 빼면 앱 코드의 logger.info 가 전부 버려진다.
configure_root_logging(config.LOG_LEVEL)
configure_db_query_logging(config.DB_QUERY_LOG_ENABLED)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Chat Core가 재사용한 Qdrant 연결을 프로세스 종료 시 정리한다."""
    yield
    qdrant_client = getattr(app.state, "chat_qdrant_client", None)
    if qdrant_client is not None:
        await qdrant_client.close()
    chat_tracer = getattr(app.state, "chat_tracer", None)
    if chat_tracer is not None:
        await chat_tracer.aclose()


app = FastAPI(
    default_response_class=ORJSONResponse,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(OcrUploadSizeLimitMiddleware)
app.add_middleware(
    ApiTimeoutMiddleware,
    router=app.router,
    default_timeout_seconds=config.API_TIMEOUT_SECONDS,
    path_prefix="/api/v1/",
)
initialize_tortoise(app)
register_exception_handlers(app)

app.include_router(v1_routers)
app.mount("/", NoCacheStaticFiles(directory=STATIC_DIR, html=True), name="static")
