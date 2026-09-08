from io import BytesIO
from pathlib import Path as FileSystemPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.dependencies.admin import AuthenticatedAdmin, require_admin, require_admin_or_staff
from app.dtos.challenges import (
    BadgeAdminListQuery,
    BadgeCreateRequest,
    BadgeImageUploadResponse,
    BadgeListResponse,
    BadgeResponse,
    BadgeUpdateRequest,
    ChallengeAdminListQuery,
    ChallengeCreateRequest,
    ChallengeListResponse,
    ChallengeResponse,
    ChallengeUpdateRequest,
    CustomChallengeTemplateAdminListQuery,
    CustomChallengeTemplateCreateRequest,
    CustomChallengeTemplateListResponse,
    CustomChallengeTemplateResponse,
    CustomChallengeTemplateUpdateRequest,
    VerificationActionRequest,
    VerificationListResponse,
    VerificationResponse,
)
from app.models.enums import ChallengeVerificationStatus
from app.services.challenge_participation import ChallengeParticipationService
from app.services.challenges import AdminChallengeService

admin_challenge_router = APIRouter(prefix="/admin", tags=["admin-challenges"])
AdminRead = Annotated[AuthenticatedAdmin, Depends(require_admin_or_staff)]
AdminCreateUpdate = Annotated[AuthenticatedAdmin, Depends(require_admin_or_staff)]
AdminWrite = Annotated[AuthenticatedAdmin, Depends(require_admin)]
BADGE_IMAGE_DIR = FileSystemPath(__file__).resolve().parents[2] / "static/media/badges"
BADGE_IMAGE_LIMIT = 2 * 1024 * 1024
BADGE_IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


async def _validated_badge_image(upload: UploadFile) -> tuple[bytes, str]:
    content = await upload.read(BADGE_IMAGE_LIMIT + 1)
    if len(content) > BADGE_IMAGE_LIMIT:
        raise HTTPException(status_code=413, detail="배지 이미지는 2MB 이하만 등록할 수 있습니다.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            extension = BADGE_IMAGE_FORMATS.get(image.format or "")
    except (UnidentifiedImageError, OSError, SyntaxError):
        extension = None
    if extension is None:
        raise HTTPException(status_code=422, detail="PNG, JPG, WebP 이미지만 등록할 수 있습니다.")
    return content, extension


@admin_challenge_router.post(
    "/badge-images",
    response_model=BadgeImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="배지 이미지 업로드",
)
async def upload_badge_image(
    image: Annotated[UploadFile, File(description="배지 이미지")],
    _: AdminCreateUpdate,
) -> BadgeImageUploadResponse:
    """배지 이미지 파일을 검증해 정적 미디어 경로에 저장한다."""
    content, extension = await _validated_badge_image(image)
    BADGE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    (BADGE_IMAGE_DIR / filename).write_bytes(content)
    return BadgeImageUploadResponse(image_path=f"media/badges/{filename}")


@admin_challenge_router.post("/badges", response_model=BadgeResponse, status_code=201, summary="배지 등록")
async def create_badge(
    request: BadgeCreateRequest,
    actor: AdminCreateUpdate,
) -> BadgeResponse:
    """공식 챌린지 완료 시 지급할 배지 정보를 등록한다."""
    return await AdminChallengeService().create_badge(request, actor.admin_id)


@admin_challenge_router.get("/badges", response_model=BadgeListResponse, summary="배지 목록 조회")
async def list_badges(
    _: AdminRead,
    query: Annotated[BadgeAdminListQuery, Query()],
) -> BadgeListResponse:
    items, total = await AdminChallengeService().list_badges(query)
    return BadgeListResponse(
        items=items,
        total_count=total,
        offset=query.offset,
        limit=query.limit,
    )


@admin_challenge_router.get("/badges/{badge_id}", response_model=BadgeResponse, summary="배지 상세 조회")
async def get_badge(badge_id: Annotated[int, Path(ge=1)], _: AdminRead) -> BadgeResponse:
    return await AdminChallengeService().get_badge(badge_id)


@admin_challenge_router.patch("/badges/{badge_id}", response_model=BadgeResponse, summary="배지 수정")
async def update_badge(
    badge_id: Annotated[int, Path(ge=1)],
    request: BadgeUpdateRequest,
    actor: AdminCreateUpdate,
) -> BadgeResponse:
    return await AdminChallengeService().update_badge(badge_id, request, actor.admin_id)


@admin_challenge_router.delete("/badges/{badge_id}", status_code=204, summary="배지 비활성화")
async def deactivate_badge(badge_id: Annotated[int, Path(ge=1)], actor: AdminWrite) -> Response:
    await AdminChallengeService().update_badge(
        badge_id,
        BadgeUpdateRequest(is_active=False),
        actor.admin_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_challenge_router.post(
    "/challenges",
    response_model=ChallengeResponse,
    status_code=201,
    summary="공식 챌린지 등록",
)
async def create_challenge(
    request: ChallengeCreateRequest,
    actor: AdminCreateUpdate,
) -> ChallengeResponse:
    """공통코드와 지급 배지를 연결해 공식 챌린지를 등록한다."""
    return await AdminChallengeService().create_challenge(request, actor.admin_id)


@admin_challenge_router.get(
    "/challenges",
    response_model=ChallengeListResponse,
    summary="공식 챌린지 목록 조회",
)
async def list_challenges(
    _: AdminRead,
    query: Annotated[ChallengeAdminListQuery, Query()],
) -> ChallengeListResponse:
    items, total = await AdminChallengeService().list_challenges(query)
    return ChallengeListResponse(
        items=items,
        total_count=total,
        offset=query.offset,
        limit=query.limit,
    )


@admin_challenge_router.get(
    "/challenges/{challenge_id}",
    response_model=ChallengeResponse,
    summary="공식 챌린지 상세 조회",
)
async def get_challenge(challenge_id: Annotated[int, Path(ge=1)], _: AdminRead) -> ChallengeResponse:
    return await AdminChallengeService().get_challenge(challenge_id)


@admin_challenge_router.patch(
    "/challenges/{challenge_id}",
    response_model=ChallengeResponse,
    summary="공식 챌린지 수정",
)
async def update_challenge(
    challenge_id: Annotated[int, Path(ge=1)],
    request: ChallengeUpdateRequest,
    actor: AdminCreateUpdate,
) -> ChallengeResponse:
    return await AdminChallengeService().update_challenge(challenge_id, request, actor.admin_id)


@admin_challenge_router.post(
    "/custom-challenge-templates",
    response_model=CustomChallengeTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="맞춤 챌린지 템플릿 등록",
)
async def create_custom_challenge_template(
    request: CustomChallengeTemplateCreateRequest,
    actor: AdminCreateUpdate,
) -> CustomChallengeTemplateResponse:
    """사용자 맞춤 챌린지 생성에 사용할 관리 템플릿을 등록한다."""
    return await AdminChallengeService().create_custom_template(request, actor.admin_id)


@admin_challenge_router.get(
    "/custom-challenge-templates",
    response_model=CustomChallengeTemplateListResponse,
    summary="맞춤 챌린지 템플릿 목록 조회",
)
async def list_custom_challenge_templates(
    _: AdminRead,
    query: Annotated[CustomChallengeTemplateAdminListQuery, Query()],
) -> CustomChallengeTemplateListResponse:
    items, total = await AdminChallengeService().list_custom_templates(query)
    return CustomChallengeTemplateListResponse(
        items=items,
        total_count=total,
        offset=query.offset,
        limit=query.limit,
    )


@admin_challenge_router.get(
    "/custom-challenge-templates/{template_id}",
    response_model=CustomChallengeTemplateResponse,
    summary="맞춤 챌린지 템플릿 상세 조회",
)
async def get_custom_challenge_template(
    template_id: Annotated[int, Path(ge=1)],
    _: AdminRead,
) -> CustomChallengeTemplateResponse:
    return await AdminChallengeService().get_custom_template(template_id)


@admin_challenge_router.patch(
    "/custom-challenge-templates/{template_id}",
    response_model=CustomChallengeTemplateResponse,
    summary="맞춤 챌린지 템플릿 수정",
)
async def update_custom_challenge_template(
    template_id: Annotated[int, Path(ge=1)],
    request: CustomChallengeTemplateUpdateRequest,
    actor: AdminCreateUpdate,
) -> CustomChallengeTemplateResponse:
    return await AdminChallengeService().update_custom_template(
        template_id,
        request,
        actor.admin_id,
    )


@admin_challenge_router.delete(
    "/challenges/{challenge_id}",
    status_code=204,
    summary="공식 챌린지 삭제",
)
async def delete_challenge(challenge_id: Annotated[int, Path(ge=1)], actor: AdminWrite) -> Response:
    await AdminChallengeService().delete_challenge(challenge_id, actor.admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_challenge_router.post(
    "/challenge-verifications/{verification_id}/actions",
    response_model=VerificationResponse,
    summary="챌린지 인증 승인·반려",
)
async def review_challenge_verification(
    verification_id: Annotated[int, Path(ge=1)],
    request: VerificationActionRequest,
    actor: AdminWrite,
) -> VerificationResponse:
    """MANUAL 방식으로 제출된 챌린지 인증을 승인하거나 반려한다."""
    return await ChallengeParticipationService().review_verification(
        verification_id,
        request,
        actor.admin_id,
    )


@admin_challenge_router.get(
    "/challenge-verifications",
    response_model=VerificationListResponse,
    summary="챌린지 인증 검토 목록 조회",
)
async def list_challenge_verifications(
    _: AdminRead,
    verification_status: Annotated[
        ChallengeVerificationStatus | None,
        Query(alias="status"),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> VerificationListResponse:
    """MANUAL 인증의 처리 상태별 검토 목록을 조회한다."""
    items, total = await ChallengeParticipationService().list_verifications(
        status=verification_status,
        offset=offset,
        limit=limit,
    )
    return VerificationListResponse(items=items, total_count=total, offset=offset, limit=limit)
