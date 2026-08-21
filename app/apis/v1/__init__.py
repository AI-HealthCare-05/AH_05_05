from fastapi import APIRouter

from app.apis.v1.alarm_router import alarm_router
from app.apis.v1.auth_routers import auth_router
from app.apis.v1.job_router import job_router
from app.apis.v1.user_routers import user_router

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(auth_router)
v1_routers.include_router(user_router)
v1_routers.include_router(alarm_router)
v1_routers.include_router(job_router)
