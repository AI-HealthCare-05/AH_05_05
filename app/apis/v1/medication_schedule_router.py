from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.dependencies.security import get_request_user
from app.dtos.medication_schedule import (
    MedicationScheduleResponse,
    SaveMedicationScheduleRequest,
    SaveMedicationScheduleResponse,
)
from app.models.users import User
from app.services.medication_schedule import MedicationScheduleService

medication_schedule_router = APIRouter(prefix="/med/medication", tags=["medications"])


def get_medication_schedule_service() -> MedicationScheduleService:
    return MedicationScheduleService()


@medication_schedule_router.get(
    "/schedule/{record_id}",
    response_model=MedicationScheduleResponse,
    summary="복약 시간표 조회",
)
async def get_medication_schedule(
    user: Annotated[User, Depends(get_request_user)],
    record_id: Annotated[int, Path(ge=1)],
    service: Annotated[MedicationScheduleService, Depends(get_medication_schedule_service)],
) -> MedicationScheduleResponse:
    return await service.get(user, record_id)


@medication_schedule_router.put(
    "/schedule/{record_id}",
    response_model=SaveMedicationScheduleResponse,
    summary="복약 시간표 저장",
)
async def save_medication_schedule(
    request: SaveMedicationScheduleRequest,
    record_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationScheduleService, Depends(get_medication_schedule_service)],
) -> SaveMedicationScheduleResponse:
    await service.save(user, record_id, request)
    return SaveMedicationScheduleResponse()
