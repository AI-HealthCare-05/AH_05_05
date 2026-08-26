from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.security import get_request_user
from app.dtos.medication_overview import MedicationOverviewResponse
from app.dtos.medication_schedule import (
    MedicationScheduleResponse,
    MedicationScheduleSaveRequest,
    MedicationScheduleSaveResponse,
)
from app.models.users import User
from app.services.medication_overviews import MedicationOverviewService
from app.services.medication_schedules import MedicationScheduleService

medication_schedule_router = APIRouter(prefix="/medications", tags=["medication-schedule"])


def get_medication_schedule_service() -> MedicationScheduleService:
    return MedicationScheduleService()


def get_medication_overview_service() -> MedicationOverviewService:
    return MedicationOverviewService()


@medication_schedule_router.get(
    "",
    response_model=list[MedicationOverviewResponse],
    response_model_by_alias=True,
    summary="복약 개요 목록 조회",
)
async def list_medication_overviews(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationOverviewService, Depends(get_medication_overview_service)],
) -> list[MedicationOverviewResponse]:
    return await service.list_overviews(user)


@medication_schedule_router.get(
    "/schedule",
    response_model=MedicationScheduleResponse,
    response_model_by_alias=True,
    summary="복약 시간 설정 조회",
)
async def get_medication_schedule(
    record_id: Annotated[int, Query(alias="recordId", gt=0)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationScheduleService, Depends(get_medication_schedule_service)],
) -> MedicationScheduleResponse:
    return await service.get_schedule(user, record_id)


@medication_schedule_router.put(
    "/schedule",
    response_model=MedicationScheduleSaveResponse,
    response_model_by_alias=True,
    summary="복약 시간 설정 저장",
)
async def save_medication_schedule(
    request: MedicationScheduleSaveRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationScheduleService, Depends(get_medication_schedule_service)],
) -> MedicationScheduleSaveResponse:
    return await service.save_schedule(user, request)
