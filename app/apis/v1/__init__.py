from fastapi import APIRouter

from app.apis.v1.admin_auth_routers import admin_auth_router
from app.apis.v1.admin_routers import admin_router
from app.apis.v1.alarm_router import alarm_router
from app.apis.v1.auth_routers import auth_router
from app.apis.v1.chat_router import chat_router
from app.apis.v1.job_router import job_router
from app.apis.v1.med_router import med_router
from app.apis.v1.medication_guide_ocr_router import medication_guide_ocr_router
from app.apis.v1.user_routers import user_router

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(auth_router)
v1_routers.include_router(chat_router)
v1_routers.include_router(user_router)
v1_routers.include_router(alarm_router)
v1_routers.include_router(job_router)
v1_routers.include_router(medication_guide_ocr_router)
v1_routers.include_router(med_router)
v1_routers.include_router(admin_auth_router)
v1_routers.include_router(admin_router)
