from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.internal_auth import require_internal_api_key
from app.dtos.background_jobs import (
    BackgroundJobFilter,
    BackgroundJobListResponse,
    BackgroundJobResponse,
    BackgroundJobStatsResponse,
)
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.services.background_jobs import BackgroundJobService

job_router = APIRouter(
    prefix="/internal/jobs",
    tags=["internal-jobs"],
    dependencies=[Depends(require_internal_api_key)],
)


def get_background_job_service() -> BackgroundJobService:
    return BackgroundJobService()


@job_router.get("", response_model=BackgroundJobListResponse, summary="백그라운드 작업 목록 조회")
async def list_background_jobs(
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
    job_type: BackgroundJobType | None = None,
    job_status: Annotated[BackgroundJobStatus | None, Query(alias="status")] = None,
    user_id: Annotated[int | None, Query(gt=0)] = None,
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BackgroundJobListResponse:
    """내부 운영 시스템이 유형·상태·사용자·요청 기간으로 백그라운드 작업을 조회한다."""
    filters = BackgroundJobFilter(
        job_type=job_type,
        status=job_status,
        user_id=user_id,
        requested_from=requested_from,
        requested_to=requested_to,
        offset=offset,
        limit=limit,
    )
    jobs, total = await service.list(filters)
    return BackgroundJobListResponse(
        items=[BackgroundJobResponse.model_validate(job) for job in jobs],
        total=total,
        offset=offset,
        limit=limit,
    )


@job_router.get("/stats", response_model=BackgroundJobStatsResponse, summary="백그라운드 작업 상태별 통계 조회")
async def get_background_job_stats(
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
    start_date: date,
    end_date: date,
) -> BackgroundJobStatsResponse:
    """내부 운영 시스템이 생성일 범위에 포함된 백그라운드 작업을 상태별로 집계한다."""
    return await service.stats(start_date, end_date)


@job_router.get("/{job_id}", response_model=BackgroundJobResponse, summary="백그라운드 작업 상세 조회")
async def get_background_job(
    job_id: int,
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> BackgroundJobResponse:
    """내부 운영 시스템이 작업 한 건의 실행 상태·재시도 횟수·오류 정보를 조회한다."""
    return BackgroundJobResponse.model_validate(await service.get(job_id))


@job_router.post(
    "/{job_id}/retry",
    response_model=BackgroundJobResponse,
    summary="실패한 백그라운드 작업 재시도",
)
async def retry_background_job(
    job_id: int,
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> BackgroundJobResponse:
    """실패한 작업을 원본과 연결된 새 자식 작업으로 생성하고 ARQ 큐에 다시 등록한다."""
    return BackgroundJobResponse.model_validate(await service.retry_failed(job_id))


@job_router.post(
    "/{job_id}/cancel",
    response_model=BackgroundJobResponse,
    summary="대기 중인 백그라운드 작업 취소",
)
async def cancel_background_job(
    job_id: int,
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> BackgroundJobResponse:
    """아직 실행되지 않은 QUEUED 또는 RETRY_WAITING 작업을 취소 상태로 전환한다."""
    return BackgroundJobResponse.model_validate(await service.cancel(job_id))
