from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core import config
from app.core.db.databases import initialize_tortoise
from app.core.exception_handlers import register_exception_handlers
from app.core.logger import configure_db_query_logging

STATIC_DIR = Path(__file__).resolve().parent / "static"

configure_db_query_logging(config.DB_QUERY_LOG_ENABLED)

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)
register_exception_handlers(app)

app.include_router(v1_routers)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
