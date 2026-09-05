from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.security import get_request_user
from app.dtos.nutrient_standards import NutrientStandardListResponse, NutrientStandardResponse
from app.dtos.supplement_doses import SupplementDoseRequest, SupplementDoseResponse
from app.dtos.supplement_nutrients import (
    PopularSupplementNutrientResponse,
    SupplementNutrientListResponse,
    SupplementNutrientResponse,
)
from app.dtos.supplement_reviews import SupplementReviewListResponse
from app.dtos.user_supplement_nutrients import (
    ManualSupplementNutrientCreateRequest,
    UserSupplementNutrientListResponse,
    UserSupplementNutrientResponse,
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.models.enums import SupplementStatus
from app.models.users import User
from app.repositories.supplement_nutrient_repository import SupplementSort
from app.services.nutrient_standards import NutrientStandardService
from app.services.supplement_doses import SupplementDoseService
from app.services.supplement_nutrients import SupplementNutrientService
from app.services.supplement_reviews import SupplementReviewService
from app.services.user_supplement_nutrients import UserSupplementNutrientService

med_router = APIRouter(prefix="/med", tags=["med-nutrition"])


@med_router.get("/supplement-doses", response_model=list[SupplementDoseResponse], summary="영양제 일일 복용 기록 조회")
async def list_supplement_doses(
    user: Annotated[User, Depends(get_request_user)],
    dose_date: Annotated[date, Query(alias="date")],
) -> list[SupplementDoseResponse]:
    return await SupplementDoseService().list(user, dose_date)


@med_router.put("/supplement-doses", response_model=SupplementDoseResponse, summary="영양제 복용 기록 저장·되돌리기")
async def save_supplement_dose(
    data: SupplementDoseRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> SupplementDoseResponse:
    return await SupplementDoseService().save(user, data)


def get_supplement_nutrient_service() -> SupplementNutrientService:
    return SupplementNutrientService()


def get_nutrient_standard_service() -> NutrientStandardService:
    return NutrientStandardService()


def get_user_supplement_nutrient_service() -> UserSupplementNutrientService:
    return UserSupplementNutrientService()


def get_supplement_review_service() -> SupplementReviewService:
    return SupplementReviewService()


@med_router.get(
    "/nutr-std",
    response_model=NutrientStandardListResponse,
    summary="한국인 영양소 섭취기준 목록 조회",
)
async def list_nutrient_standards(
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NutrientStandardService, Depends(get_nutrient_standard_service)],
    grp: Annotated[str | None, Query(min_length=1, max_length=10, description="대상 구분")] = None,
    age: Annotated[int | None, Query(ge=1, description="만 나이(1세 이상)")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NutrientStandardListResponse:
    """2025 한국인 영양소 섭취기준을 대상 구분·연령 조건과 페이지 단위로 조회한다."""
    standards, total = await service.list(grp=grp, age=age, offset=offset, limit=limit)
    return NutrientStandardListResponse(
        items=[NutrientStandardResponse.model_validate(item) for item in standards],
        total=total,
        offset=offset,
        limit=limit,
    )


@med_router.get(
    "/nutr",
    response_model=SupplementNutrientListResponse,
    summary="건강기능식품 영양성분 검색",
)
async def search_supplement_nutrients(
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementNutrientService, Depends(get_supplement_nutrient_service)],
    name: Annotated[str, Query(min_length=1, max_length=100)],
    sort: Annotated[SupplementSort, Query(description="검색 결과 정렬 기준")] = "name",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SupplementNutrientListResponse:
    """제품명 앞뒤 부분 검색으로 건강기능식품 기준정보를 페이지 단위로 조회한다."""
    products, total = await service.search(name, sort=sort, offset=offset, limit=limit)
    return SupplementNutrientListResponse(
        items=[SupplementNutrientResponse.model_validate(product) for product in products],
        total=total,
        offset=offset,
        limit=limit,
    )


@med_router.get(
    "/nutr/popular",
    response_model=list[PopularSupplementNutrientResponse],
    summary="현재 가장 많이 복용 중인 영양제 조회",
)
async def list_popular_supplement_nutrients(
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementNutrientService, Depends(get_supplement_nutrient_service)],
) -> list[PopularSupplementNutrientResponse]:
    """현재 복용 중인 사용자 수가 많은 영양제 상위 5개의 ID와 이름을 조회한다."""
    products = await service.list_popular()
    return [PopularSupplementNutrientResponse(id=product.id, name=product.name) for product in products]


@med_router.post(
    "/nutr/reviews/{registration_id}/report",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="영양제 후기 신고",
)
async def report_supplement_review(
    registration_id: Annotated[int, Path(ge=1, description="신고할 사용자 영양제 등록 ID")],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementReviewService, Depends(get_supplement_review_service)],
) -> Response:
    """공개 후기 한 건을 신고한다. 같은 사용자의 재시도는 멱등하게 처리한다."""
    await service.report(user, registration_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@med_router.get(
    "/nutr/{supplement_nutrient_id}/reviews",
    response_model=SupplementReviewListResponse,
    summary="영양제 공개 후기 목록 조회",
)
async def list_supplement_reviews(
    supplement_nutrient_id: Annotated[int, Path(ge=1, description="건강기능식품 기준정보 ID")],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementReviewService, Depends(get_supplement_review_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SupplementReviewListResponse:
    """탈퇴·신고 숨김 대상을 제외한 공개 후기를 최신순으로 조회한다."""
    return await service.list(user, supplement_nutrient_id, offset=offset, limit=limit)


@med_router.get(
    "/nutr/{supplement_nutrient_id}",
    response_model=SupplementNutrientResponse,
    summary="건강기능식품 영양성분 상세 조회",
)
async def get_supplement_nutrient(
    supplement_nutrient_id: int,
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementNutrientService, Depends(get_supplement_nutrient_service)],
) -> SupplementNutrientResponse:
    """건강기능식품 한 제품의 전체 영양성분과 섭취 기준정보를 조회한다."""
    return SupplementNutrientResponse.model_validate(await service.get(supplement_nutrient_id))


@med_router.get(
    "/user-suppl-nutr",
    response_model=UserSupplementNutrientListResponse,
    summary="영양제 복용 정보 목록 조회",
)
async def list_user_supplement_nutrients(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
    registration_status: Annotated[SupplementStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserSupplementNutrientListResponse:
    """현재 사용자의 영양제 복용 정보를 상태 조건과 페이지 단위로 조회한다."""
    return await service.list(
        user,
        registration_status=registration_status,
        offset=offset,
        limit=limit,
    )


@med_router.post(
    "/user-suppl-nutr",
    response_model=UserSupplementNutrientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="표준데이터에 없는 영양제 직접 등록",
)
async def create_manual_user_supplement_nutrient(
    data: ManualSupplementNutrientCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
) -> UserSupplementNutrientResponse:
    """표준데이터에서 찾지 못한 제품을 이름만으로 등록한다. 성분 합계에는 포함하지 않는다."""
    return await service.create_manual(user, data)


@med_router.put(
    "/user-suppl-nutr/{registration_id}",
    response_model=UserSupplementNutrientResponse,
    summary="영양제 복용 정보 등록 또는 재등록",
)
async def upsert_user_supplement_nutrient(
    registration_id: Annotated[
        int,
        Path(ge=1, description="등록할 supplement_nutrients 제품 ID"),
    ],
    data: UserSupplementNutrientUpsertRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
) -> UserSupplementNutrientResponse:
    """제품 ID를 기준으로 복용 정보를 새로 등록하거나 기존 정보를 활성 상태로 갱신한다."""
    return await service.upsert(user, registration_id, data)


@med_router.get(
    "/user-suppl-nutr/{registration_id}",
    response_model=UserSupplementNutrientResponse,
    summary="영양제 복용 정보 상세 조회",
)
async def get_user_supplement_nutrient(
    registration_id: Annotated[int, Path(ge=1, description="사용자 복용 정보 ID")],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
) -> UserSupplementNutrientResponse:
    """현재 사용자가 소유한 영양제 복용 정보 한 건과 복용 시간대를 조회한다."""
    return await service.get(user, registration_id)


@med_router.patch(
    "/user-suppl-nutr/{registration_id}",
    response_model=UserSupplementNutrientResponse,
    summary="영양제 복용 정보 수정",
)
async def update_user_supplement_nutrient(
    registration_id: Annotated[int, Path(ge=1, description="사용자 복용 정보 ID")],
    data: UserSupplementNutrientUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
) -> UserSupplementNutrientResponse:
    """복용량·기간·상태·시간대·메모 중 전달된 항목만 수정한다."""
    return await service.update(user, registration_id, data)


@med_router.delete(
    "/user-suppl-nutr/{registration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="영양제 복용 완료 처리",
)
async def complete_user_supplement_nutrient(
    registration_id: Annotated[int, Path(ge=1, description="사용자 복용 정보 ID")],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserSupplementNutrientService, Depends(get_user_supplement_nutrient_service)],
) -> Response:
    """복용 정보를 물리적으로 삭제하지 않고 COMPLETED 상태와 종료일을 기록한다."""
    await service.complete(user, registration_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
