from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core import config
from app.dependencies.security import get_request_user
from app.dtos.alarms import (
    AlarmActionRequest,
    AlarmCreateRequest,
    AlarmEventListResponse,
    AlarmEventResponse,
    AlarmListResponse,
    AlarmResponse,
    AlarmUpdateRequest,
    DeliveryAckRequest,
    PushPublicKeyResponse,
    PushSubscriptionListResponse,
    PushSubscriptionResponse,
    PushSubscriptionUpsertRequest,
)
from app.models.enums import AlarmStatus, AlarmType
from app.models.users import User
from app.services.alarms import AlarmAction, AlarmService

alarm_router = APIRouter(prefix="/alarms", tags=["alarms"])


def get_alarm_service() -> AlarmService:
    return AlarmService()


@alarm_router.get(
    "/push-public-key",
    response_model=PushPublicKeyResponse,
    summary="Web Push 공개키 조회",
)
async def get_push_public_key(
    _user: Annotated[User, Depends(get_request_user)],
) -> PushPublicKeyResponse:
    """브라우저가 PushManager 구독을 생성할 때 필요한 VAPID 공개키를 반환한다."""
    return PushPublicKeyResponse(public_key=config.VAPID_PUBLIC_KEY)


@alarm_router.put(
    "/push-subscriptions",
    response_model=PushSubscriptionResponse,
    summary="Web Push 구독 등록 또는 갱신",
)
async def upsert_push_subscription(
    data: PushSubscriptionUpsertRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> PushSubscriptionResponse:
    """현재 사용자의 브라우저 Push 구독을 endpoint 기준으로 등록하거나 키 정보를 갱신한다."""
    subscription = await service.upsert_subscription(user, data)
    return PushSubscriptionResponse.model_validate(subscription)


@alarm_router.get(
    "/push-subscriptions",
    response_model=PushSubscriptionListResponse,
    summary="Web Push 구독 목록 조회",
)
async def list_push_subscriptions(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> PushSubscriptionListResponse:
    """현재 사용자에게 등록된 활성·비활성 Web Push 구독 목록을 조회한다."""
    subscriptions = await service.list_subscriptions(user)
    return PushSubscriptionListResponse(
        items=[PushSubscriptionResponse.model_validate(item) for item in subscriptions]
    )


@alarm_router.delete(
    "/push-subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Web Push 구독 해제",
)
async def deactivate_push_subscription(
    subscription_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> Response:
    """지정한 Push 구독을 삭제하지 않고 비활성화하여 이후 알림 발송에서 제외한다."""
    await service.deactivate_subscription(user, subscription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@alarm_router.post(
    "",
    response_model=AlarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="알람 생성",
)
async def create_alarm(
    data: AlarmCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> AlarmResponse:
    """현재 사용자에게 단일 또는 반복 알람을 생성하고 최초 예약 이벤트를 기록한다."""
    alarm = await service.create_alarm(user, data)
    return AlarmResponse.model_validate(alarm)


@alarm_router.get("", response_model=AlarmListResponse, summary="알람 목록 조회")
async def list_alarms(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
    alarm_status: Annotated[AlarmStatus | None, Query(alias="status")] = None,
    alarm_type: AlarmType | None = None,
    care_episode_id: int | None = None,
    follow_up_visit_id: int | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AlarmListResponse:
    """상태·유형·케어 에피소드 조건으로 현재 사용자의 알람을 페이지 단위로 조회한다."""
    alarms, total = await service.list_alarms(
        user,
        alarm_status=alarm_status,
        alarm_type=alarm_type,
        care_episode_id=care_episode_id,
        follow_up_visit_id=follow_up_visit_id,
        offset=offset,
        limit=limit,
    )
    return AlarmListResponse(
        items=[AlarmResponse.model_validate(alarm) for alarm in alarms],
        total=total,
        offset=offset,
        limit=limit,
    )


@alarm_router.get("/{alarm_id}", response_model=AlarmResponse, summary="알람 상세 조회")
async def get_alarm(
    alarm_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> AlarmResponse:
    """현재 사용자가 소유한 알람 한 건의 예약 시간과 상태를 조회한다."""
    return AlarmResponse.model_validate(await service.get_alarm(user, alarm_id))


@alarm_router.patch("/{alarm_id}", response_model=AlarmResponse, summary="알람 수정")
async def update_alarm(
    alarm_id: int,
    data: AlarmUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> AlarmResponse:
    """알람 제목·메시지·예약·반복 규칙 등 전달된 항목만 수정한다."""
    return AlarmResponse.model_validate(await service.update_alarm(user, alarm_id, data))


@alarm_router.delete(
    "/{alarm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="알람 삭제",
)
async def cancel_alarm(
    alarm_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> Response:
    """알람을 물리적으로 삭제하지 않고 CANCELLED 상태로 전환하여 소프트 삭제한다."""
    await service.cancel_alarm(user, alarm_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@alarm_router.post(
    "/{alarm_id}/actions",
    response_model=AlarmResponse,
    summary="알람 업무 동작 실행",
)
async def execute_alarm_action(
    alarm_id: int,
    data: AlarmActionRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> AlarmResponse:
    """pause·resume·complete·skip 중 하나를 실행하고 변경된 알람 상태를 반환한다."""
    alarm = await service.transition(user, alarm_id, AlarmAction(data.action))
    return AlarmResponse.model_validate(alarm)


@alarm_router.get(
    "/{alarm_id}/events",
    response_model=AlarmEventListResponse,
    summary="알람 이벤트 이력 조회",
)
async def list_alarm_events(
    alarm_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AlarmEventListResponse:
    """예약·발송·실패·수신 확인 등 알람의 전체 처리 이력을 페이지 단위로 조회한다."""
    events, total = await service.list_events(user, alarm_id, offset=offset, limit=limit)
    return AlarmEventListResponse(
        items=[AlarmEventResponse.model_validate(event) for event in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@alarm_router.post(
    "/{alarm_id}/delivery-ack",
    response_model=AlarmEventResponse,
    summary="알람 수신 확인 기록",
)
async def acknowledge_alarm_delivery(
    alarm_id: int,
    data: DeliveryAckRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[AlarmService, Depends(get_alarm_service)],
) -> AlarmEventResponse:
    """클라이언트가 Push 알림을 수신하거나 표시한 결과를 알람 이벤트로 기록한다."""
    return AlarmEventResponse.model_validate(await service.acknowledge_delivery(user, alarm_id, data))
