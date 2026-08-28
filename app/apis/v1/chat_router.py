import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ai_worker.schemas.medication_chat import MedicationChatProgress
from app.core.api_timeout import api_timeout
from app.core.exceptions import AppError
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

_STREAM_COMPLETE = object()

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
    504: {
        "model": ChatErrorResponse,
        "description": "20초 안에 답변 생성을 완료하지 못함",
        "content": {
            "application/json": {
                "example": {
                    "code": "API_TIMEOUT",
                    "message": "요청 처리 시간이 초과되었습니다.",
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
@api_timeout(20)
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


def _sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: {event}\ndata: {payload}\n\n"


async def _chat_event_stream(
    *,
    data: SendChatRequest,
    user: User,
    service: ChatApplicationService,
) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | object] = asyncio.Queue()

    async def report_progress(progress: MedicationChatProgress) -> None:
        await queue.put(
            (
                "progress",
                progress.model_dump(mode="json"),
            )
        )

    async def run_chat() -> None:
        try:
            result = await service.send(
                user=user,
                command=SendChatCommand(
                    request_id=str(data.request_id),
                    record_id=data.record_id,
                    conversation_id=data.conversation_id,
                    message=data.message,
                ),
                progress_callback=report_progress,
            )
            response = SendChatResponse.from_result(result)
            await queue.put(
                (
                    "complete",
                    response.model_dump(
                        mode="json",
                        by_alias=True,
                    ),
                )
            )
        except AppError as error:
            await queue.put(
                (
                    "error",
                    {
                        "code": error.code,
                        "message": error.message,
                    },
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await queue.put(
                (
                    "error",
                    {
                        "code": "CHAT_STREAM_FAILED",
                        "message": ("답변 생성 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."),
                    },
                )
            )
        finally:
            await queue.put(_STREAM_COMPLETE)

    task = asyncio.create_task(run_chat())
    try:
        while True:
            item = await queue.get()
            if item is _STREAM_COMPLETE:
                break
            event, payload = item
            yield _sse_event(event, payload)
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@chat_router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="약·영양제 근거 기반 답변 진행 상태 전송",
    description=(
        "질문 확인·근거 검색·답변 정리·안전 확인 상태만 SSE로 전달합니다. "
        "LLM 원문과 안전성 검사 전 답변은 전송하지 않으며, 전체 답변 생성과 "
        "안전성 검사가 끝난 결과만 complete 이벤트로 전달하고 저장합니다."
    ),
    responses={
        **_CHAT_RESPONSES,
        200: {
            "description": "고정 진행 상태와 검증 완료 답변을 SSE로 전송",
            "content": {
                "text/event-stream": {
                    "example": (
                        'event: progress\ndata: {"stage":"QUESTION_CHECKING",'
                        '"message":"질문 확인 중"}\n\n'
                        'event: complete\ndata: {"conversationId":42,'
                        '"messageId":101,"answer":"검증된 답변",'
                        '"sources":[]}\n\n'
                    )
                }
            },
        },
    },
)
@api_timeout(20)
async def stream_chat_answer(
    data: SendChatRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[
        ChatApplicationService,
        Depends(get_chat_application_service),
    ],
) -> StreamingResponse:
    return StreamingResponse(
        _chat_event_stream(
            data=data,
            user=user,
            service=service,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
