from fastapi import APIRouter

from app.apis.v1.admin_auth_routers import admin_auth_router
from app.apis.v1.admin_routers import admin_router
from app.apis.v1.auth_routers import auth_router
from app.apis.v1.user_routers import user_router

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(auth_router)
v1_routers.include_router(user_router)
v1_routers.include_router(admin_auth_router)
v1_routers.include_router(admin_router)
