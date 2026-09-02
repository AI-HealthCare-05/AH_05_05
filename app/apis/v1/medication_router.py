from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.security import get_request_user
from app.dtos.medications import MedicationDoseResponse, MedicationOverview, SaveMedicationDoseRequest
from app.models.users import User
from app.services.medications import MedicationService

medication_router = APIRouter(prefix="/medications", tags=["medications"])


def get_medication_service() -> MedicationService:
    return MedicationService()


@medication_router.get(
    "",
    response_model=list[MedicationOverview],
    response_model_exclude_unset=True,
    summary="복약 현황 조회",
)
async def get_medications(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[MedicationOverview]:
    return await service.list_overviews(user, from_date, to_date)


@medication_router.get(
    "/doses",
    response_model=list[MedicationDoseResponse],
    summary="복용 체크 기록 조회",
)
async def get_medication_doses(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> list[MedicationDoseResponse]:
    return await service.list_doses(user, from_date, to_date)


@medication_router.post(
    "/doses",
    response_model=MedicationDoseResponse,
    summary="복용 체크 저장 또는 되돌리기",
)
async def save_medication_dose(
    request: SaveMedicationDoseRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> MedicationDoseResponse:
    return await service.save_dose(user, request)


@medication_router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="복약 정보 취소",
)
async def cancel_medication(
    record_id: Annotated[int, Path(gt=0)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> Response:
    await service.cancel(user, record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
