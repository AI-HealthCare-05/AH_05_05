from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.security import get_request_user
from app.dtos.medications import (
    CreateMedicationNoteRequest,
    MedicationDoseResponse,
    MedicationNoteListResponse,
    MedicationNoteResponse,
    MedicationOverview,
    SaveMedicationDoseRequest,
    UpdateCareEpisodeAliasRequest,
    UpdateMedicationNoteRequest,
)
from app.models.users import User
from app.services.medications import MedicationService

medication_router = APIRouter(prefix="/medications", tags=["medications"])
medication_resource_router = APIRouter(prefix="/med", tags=["medications"])


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


@medication_resource_router.patch(
    "/episodes/{record_id}/alias",
    response_model=dict[str, str | None],
    summary="복약 처방 별칭 수정",
)
async def update_episode_alias(
    request: UpdateCareEpisodeAliasRequest,
    record_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> dict[str, str | None]:
    result = await service.update_episode_alias(user, record_id, request.alias)
    return {"alias": result.alias}


@medication_resource_router.get(
    "/notes",
    response_model=MedicationNoteListResponse,
    summary="복약 메모 목록 조회",
)
async def list_medication_notes(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
    episode_id: Annotated[int | None, Query(alias="episodeId", ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> MedicationNoteListResponse:
    return await service.list_notes_page(
        user,
        episode_id=episode_id,
        limit=limit,
        cursor=cursor,
    )


@medication_resource_router.post(
    "/notes",
    response_model=MedicationNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="복약 메모 작성",
)
async def create_medication_note(
    request: CreateMedicationNoteRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> MedicationNoteResponse:
    return await service.create_note(user, request)


@medication_resource_router.get(
    "/notes/{note_id}",
    response_model=MedicationNoteResponse,
    summary="복약 메모 상세 조회",
)
async def get_medication_note(
    note_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> MedicationNoteResponse:
    return await service.get_note(user, note_id)


@medication_resource_router.patch(
    "/notes/{note_id}",
    response_model=MedicationNoteResponse,
    summary="복약 메모 수정",
)
async def update_medication_note(
    request: UpdateMedicationNoteRequest,
    note_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> MedicationNoteResponse:
    return await service.update_note(user, note_id, request)


@medication_resource_router.delete(
    "/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="복약 메모 삭제",
)
async def delete_medication_note(
    note_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationService, Depends(get_medication_service)],
) -> Response:
    await service.delete_note(user, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
