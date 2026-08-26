from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.chat import get_chat_application_service
from app.dependencies.security import get_request_user
from app.dtos.chat import (
    ChatErrorResponse,
    SendChatRequest,
    SendChatResponse,
)
from app.models.users import User
from app.services.chat import ChatApplicationService, SendChatCommand

chat_router = APIRouter(prefix="/chat", tags=["chat"])

_CHAT_RESPONSES = {
    200: {
        "description": "근거 기반 채팅 답변 생성 및 저장 완료",
    },
    401: {
        "model": ChatErrorResponse,
        "description": "로그인이 필요하거나 인증 정보가 유효하지 않음",
        "content": {
            "application/json": {
                "example": {
                    "code": "UNAUTHORIZED",
                    "message": "인증이 필요합니다.",
                }
            }
        },
    },
    404: {
        "model": ChatErrorResponse,
        "description": "대화 또는 확정 복약 기록을 찾을 수 없음",
        "content": {
            "application/json": {
                "example": {
                    "code": "CARE_EPISODE_NOT_FOUND",
                    "message": "확인 완료된 복약 기록을 찾을 수 없습니다.",
                }
            }
        },
    },
    409: {
        "model": ChatErrorResponse,
        "description": "기존 대화 정보 또는 동일 요청 식별자와 충돌",
        "content": {
            "application/json": {
                "example": {
                    "code": "CHAT_REQUEST_IN_PROGRESS",
                    "message": "같은 채팅 요청을 처리하고 있습니다.",
                }
            }
        },
    },
    422: {
        "model": ChatErrorResponse,
        "description": "질문 또는 요청 식별자 입력값이 올바르지 않음",
        "content": {
            "application/json": {
                "example": {
                    "code": "VALIDATION_ERROR",
                    "message": "질문을 입력해 주세요.",
                    "field": "message",
                }
            }
        },
    },
    503: {
        "model": ChatErrorResponse,
        "description": "외부 답변 생성 또는 검색 서비스를 일시적으로 사용할 수 없음",
        "content": {
            "application/json": {
                "example": {
                    "code": "CHAT_UPSTREAM_UNAVAILABLE",
                    "message": "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                }
            }
        },
    },
}


@chat_router.post(
    "",
    response_model=SendChatResponse,
    summary="약·영양제 근거 기반 답변 생성",
    description=(
        "인증 사용자의 확인 완료 복약 기록과 현재 복용 영양제를 우선 조회하고, "
        "승인된 상호작용 규칙·의약품 기본정보·Qdrant 공공 근거를 조합해 답변합니다. "
        "recordId 없이도 일반 의약품·영양제 질문이 가능하며, 진단·처방·복용 변경을 "
        "대신하지 않습니다. 동일 requestId는 저장된 완료 답변을 재사용합니다."
    ),
    responses=_CHAT_RESPONSES,
)
async def answer_chat_message(
    data: SendChatRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[
        ChatApplicationService,
        Depends(get_chat_application_service),
    ],
) -> SendChatResponse:
    result = await service.send(
        user=user,
        command=SendChatCommand(
            request_id=str(data.request_id),
            record_id=data.record_id,
            conversation_id=data.conversation_id,
            message=data.message,
        ),
    )
    return SendChatResponse.from_result(result)
