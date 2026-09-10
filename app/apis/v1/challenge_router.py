from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.dependencies.security import get_request_user
from app.dtos.challenges import (
    ChallengeCatalogListResponse,
    ChallengeCatalogResponse,
    UserBadgeListResponse,
    UserChallengeListResponse,
    UserChallengeResponse,
    VerificationCreateRequest,
    VerificationResponse,
)
from app.dtos.custom_challenges import (
    CustomChallengeBadgeAwardListResponse,
    CustomChallengeJoinRequest,
    CustomChallengeParticipationListResponse,
    CustomChallengeParticipationResponse,
    CustomChallengeRecommendationListResponse,
)
from app.models.users import User
from app.services.challenge_catalog import ChallengeCatalogService
from app.services.challenge_participation import ChallengeParticipationService
from app.services.custom_challenge_badges import CustomChallengeBadgeService
from app.services.custom_challenges import CustomChallengeService

challenge_router = APIRouter(prefix="/user", tags=["user-challenges"])


@challenge_router.get(
    "/custom-challenge-recommendations",
    response_model=CustomChallengeRecommendationListResponse,
    summary="맞춤 챌린지 추천 조회",
)
async def list_custom_challenge_recommendations(
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeRecommendationListResponse:
    return await CustomChallengeService().recommendations(user)


@challenge_router.post(
    "/custom-challenge-recommendations/{template_id}/participations",
    response_model=CustomChallengeParticipationResponse,
    status_code=201,
    summary="맞춤 챌린지 참여",
)
async def join_custom_challenge(
    template_id: Annotated[int, Path(ge=1)],
    request: CustomChallengeJoinRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeParticipationResponse:
    return await CustomChallengeService().join(user, template_id, request)


@challenge_router.get(
    "/custom-challenge-participations",
    response_model=CustomChallengeParticipationListResponse,
    summary="내 맞춤 챌린지 목록 조회",
)
async def list_custom_challenge_participations(
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeParticipationListResponse:
    return await CustomChallengeService().list(user)


@challenge_router.get(
    "/custom-challenges/badges",
    response_model=CustomChallengeBadgeAwardListResponse,
    summary="내 맞춤 챌린지 배지 목록 조회",
)
async def list_custom_challenge_badges(
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeBadgeAwardListResponse:
    return await CustomChallengeBadgeService().list_for_user(user.id)


@challenge_router.get(
    "/custom-challenge-participations/{participation_id}",
    response_model=CustomChallengeParticipationResponse,
    summary="내 맞춤 챌린지 상세 조회",
)
async def get_custom_challenge_participation(
    participation_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeParticipationResponse:
    return await CustomChallengeService().get(user, participation_id)


@challenge_router.post(
    "/custom-challenge-participations/{participation_id}/cancel",
    response_model=CustomChallengeParticipationResponse,
    summary="맞춤 챌린지 참여 취소",
)
async def cancel_custom_challenge_participation(
    participation_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> CustomChallengeParticipationResponse:
    return await CustomChallengeService().cancel(user, participation_id)


@challenge_router.get(
    "/challenge-catalog", response_model=ChallengeCatalogListResponse, summary="게시된 공식 챌린지 조회"
)
async def list_challenge_catalog(
    user: Annotated[User, Depends(get_request_user)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ChallengeCatalogListResponse:
    items, total = await ChallengeCatalogService().list(user.id, offset, limit)
    return ChallengeCatalogListResponse(items=items, total_count=total, offset=offset, limit=limit)


@challenge_router.get("/challenge-catalog/{challenge_id}", response_model=ChallengeCatalogResponse)
async def get_challenge_catalog(
    challenge_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> ChallengeCatalogResponse:
    return await ChallengeCatalogService().get(user.id, challenge_id)


@challenge_router.post(
    "/challenges/{challenge_id}/join",
    response_model=UserChallengeResponse,
    status_code=201,
    summary="공식 챌린지 참여",
)
async def join_challenge(
    challenge_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> UserChallengeResponse:
    """현재 사용자가 모집 중인 공식 챌린지에 참여하고 진행 구간을 생성한다."""
    return await ChallengeParticipationService().join(user, challenge_id)


@challenge_router.get("/challenges", response_model=UserChallengeListResponse, summary="내 챌린지 목록 조회")
async def list_my_challenges(
    user: Annotated[User, Depends(get_request_user)],
) -> UserChallengeListResponse:
    items = await ChallengeParticipationService().list(user)
    return UserChallengeListResponse(items=items, total_count=len(items))


@challenge_router.get(
    "/challenges/{participation_id}",
    response_model=UserChallengeResponse,
    summary="내 챌린지 상세 조회",
)
async def get_my_challenge(
    participation_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> UserChallengeResponse:
    return await ChallengeParticipationService().get(user, participation_id)


@challenge_router.post(
    "/challenges/{participation_id}/verifications",
    response_model=VerificationResponse,
    status_code=201,
    summary="챌린지 인증 제출",
)
async def submit_challenge_verification(
    participation_id: Annotated[int, Path(ge=1)],
    request: VerificationCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> VerificationResponse:
    """인증일을 기준으로 현재 사용자의 진행 구간에 인증 기록을 제출한다."""
    return await ChallengeParticipationService().submit_verification(user, participation_id, request)


@challenge_router.post(
    "/challenges/{participation_id}/cancel",
    response_model=UserChallengeResponse,
    summary="챌린지 참여 취소",
)
async def cancel_challenge(
    participation_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
) -> UserChallengeResponse:
    return await ChallengeParticipationService().cancel(user, participation_id)


@challenge_router.get("/badges", response_model=UserBadgeListResponse, summary="내 배지 목록 조회")
async def list_my_badges(
    user: Annotated[User, Depends(get_request_user)],
) -> UserBadgeListResponse:
    items = await ChallengeParticipationService().list_badges(user)
    return UserBadgeListResponse(items=items, total_count=len(items))
