from dataclasses import dataclass
from decimal import Decimal

from tortoise.timezone import now
from tortoise.transactions import in_transaction

from ai_worker.schemas.medication_chat import (
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from app.models.care import CareEpisode
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatMessageStatus,
    ChatRouteType,
    ChatSafetyStatus,
    ChatSessionStatus,
    ChatSourceType,
    PatientSourceKind,
)
from app.models.users import User


class ChatRepositoryError(RuntimeError):
    pass


class ChatSessionNotFoundError(ChatRepositoryError):
    pass


class CareEpisodeNotFoundError(ChatRepositoryError):
    pass


class ChatContextMismatchError(ChatRepositoryError):
    pass


class ChatRequestInProgressError(ChatRepositoryError):
    pass


class ChatRequestPayloadMismatchError(ChatRepositoryError):
    pass


@dataclass(slots=True)
class AcceptedChatRequest:
    session: ChatSession
    user_message: ChatMessage | None
    assistant_message: ChatMessage | None
    history: list[ChatMessage]
    reused_assistant_message: ChatMessage | None = None


class ChatRepository:
    async def accept_request(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
        conversation_id: int | None,
        request_id: str,
        content: str,
    ) -> AcceptedChatRequest:
        async with in_transaction() as connection:
            episode = await self._get_owned_confirmed_episode(
                user_id=user_id,
                care_episode_id=care_episode_id,
                connection=connection,
            )
            # 첫 요청의 응답을 받기 전에 네트워크가 끊기면 클라이언트는
            # conversationId 없이 같은 requestId를 재시도한다. 사용자 행을
            # 짧게 잠가 수락 단계를 직렬화하고 모든 세션에서 기존 요청을 찾는다.
            await User.filter(id=user_id).using_db(connection).select_for_update().get()
            existing = (
                await ChatMessage.filter(
                    chat_session__user_id=user_id,
                    request_id=request_id,
                    role=ChatMessageRole.ASSISTANT,
                )
                .using_db(connection)
                .select_related("chat_session", "reply_to_message")
                .order_by("-id")
                .first()
            )
            if existing is not None:
                self._validate_existing_request(
                    existing=existing,
                    care_episode_id=care_episode_id,
                    conversation_id=conversation_id,
                    content=content,
                )
                if existing.status == ChatMessageStatus.COMPLETED:
                    return AcceptedChatRequest(
                        session=existing.chat_session,
                        user_message=None,
                        assistant_message=None,
                        history=[],
                        reused_assistant_message=existing,
                    )
                if existing.status in {
                    ChatMessageStatus.PENDING,
                    ChatMessageStatus.STREAMING,
                }:
                    raise ChatRequestInProgressError
                # 실패 요청은 동일 세션에서 다시 처리한다. 이를 통해 첫 응답을
                # 받지 못한 클라이언트도 기존 대화를 복구한다.
                conversation_id = existing.chat_session_id
            session = await self._get_or_create_session(
                user_id=user_id,
                episode=episode,
                requested_care_episode_id=care_episode_id,
                conversation_id=conversation_id,
                connection=connection,
            )
            session = (
                await ChatSession.filter(
                    id=session.id,
                )
                .using_db(connection)
                .select_for_update()
                .get()
            )

            history = (
                await ChatMessage.filter(
                    chat_session_id=session.id,
                    status=ChatMessageStatus.COMPLETED,
                    role__in=[
                        ChatMessageRole.USER,
                        ChatMessageRole.ASSISTANT,
                    ],
                )
                .using_db(connection)
                .order_by("-sequence_no")
                .limit(10)
            )
            history.reverse()
            last_message = (
                await ChatMessage.filter(
                    chat_session_id=session.id,
                )
                .using_db(connection)
                .order_by("-sequence_no")
                .first()
            )
            last_sequence = last_message.sequence_no if last_message is not None else 0
            timestamp = now()
            user_message = await ChatMessage.create(
                chat_session=session,
                sequence_no=last_sequence + 1,
                role=ChatMessageRole.USER,
                content=content.strip(),
                status=ChatMessageStatus.COMPLETED,
                safety_status=ChatSafetyStatus.SAFE,
                started_at=timestamp,
                completed_at=timestamp,
                using_db=connection,
            )
            assistant_message = await ChatMessage.create(
                chat_session=session,
                reply_to_message=user_message,
                request_id=request_id,
                sequence_no=last_sequence + 2,
                role=ChatMessageRole.ASSISTANT,
                content="",
                status=ChatMessageStatus.PENDING,
                safety_status=ChatSafetyStatus.PENDING,
                started_at=timestamp,
                using_db=connection,
            )
            session.last_message_at = timestamp
            session.updated_at = timestamp
            await session.save(
                using_db=connection,
                update_fields=["last_message_at", "updated_at"],
            )
            return AcceptedChatRequest(
                session=session,
                user_message=user_message,
                assistant_message=assistant_message,
                history=history,
            )

    @staticmethod
    def _validate_existing_request(
        *,
        existing: ChatMessage,
        care_episode_id: int | None,
        conversation_id: int | None,
        content: str,
    ) -> None:
        if conversation_id is not None and existing.chat_session_id != conversation_id:
            raise ChatRequestPayloadMismatchError
        if care_episode_id is not None and existing.chat_session.care_episode_id != care_episode_id:
            raise ChatRequestPayloadMismatchError
        original = existing.reply_to_message
        if original is None or original.content != content.strip():
            raise ChatRequestPayloadMismatchError

    async def complete_request(
        self,
        *,
        assistant_message_id: int,
        result: MedicationChatResult,
        duration_ms: int,
    ) -> ChatMessage:
        async with in_transaction() as connection:
            message = (
                await ChatMessage.filter(
                    id=assistant_message_id,
                    role=ChatMessageRole.ASSISTANT,
                )
                .using_db(connection)
                .select_for_update()
                .get()
            )
            timestamp = now()
            message.content = result.answer
            message.status = ChatMessageStatus.COMPLETED
            message.route_type = self._chat_route(result)
            message.safety_status = ChatSafetyStatus(result.safety_status.value)
            message.safety_reason_code = result.safety_reason_codes[0] if result.safety_reason_codes else None
            message.model_name = result.model_name
            message.model_version = result.model_version
            message.prompt_version = result.prompt_version
            message.schema_version = result.schema_version
            message.patient_context_hash = result.context_hash
            message.duration_ms = duration_ms
            message.completed_at = timestamp
            message.updated_at = timestamp
            await message.save(
                using_db=connection,
                update_fields=[
                    "content",
                    "status",
                    "route_type",
                    "safety_status",
                    "safety_reason_code",
                    "model_name",
                    "model_version",
                    "prompt_version",
                    "schema_version",
                    "patient_context_hash",
                    "duration_ms",
                    "completed_at",
                    "updated_at",
                ],
            )
            await (
                ChatMessageSource.filter(
                    chat_message_id=message.id,
                )
                .using_db(connection)
                .delete()
            )
            for citation_order, source in enumerate(
                result.sources,
                start=1,
            ):
                await ChatMessageSource.create(
                    chat_message=message,
                    citation_order=citation_order,
                    using_db=connection,
                    **self._source_payload(source),
                )
            await (
                ChatSession.filter(id=message.chat_session_id)
                .using_db(connection)
                .update(
                    last_message_at=timestamp,
                    updated_at=timestamp,
                )
            )
        return await ChatMessage.get(id=assistant_message_id)

    async def fail_request(
        self,
        *,
        assistant_message_id: int,
        error_code: str,
        duration_ms: int,
    ) -> None:
        timestamp = now()
        await ChatMessage.filter(
            id=assistant_message_id,
            role=ChatMessageRole.ASSISTANT,
        ).update(
            status=ChatMessageStatus.FAILED,
            safety_status=ChatSafetyStatus.VALIDATION_FAILED,
            error_code=error_code,
            duration_ms=duration_ms,
            completed_at=timestamp,
            updated_at=timestamp,
        )

    async def get_message_sources(
        self,
        *,
        message_id: int,
    ) -> list[ChatMessageSource]:
        return (
            await ChatMessageSource.filter(
                chat_message_id=message_id,
            )
            .order_by("citation_order")
            .prefetch_related(
                "medication",
                "user_suppl_nutrient__supplement_nutrient",
                "interaction_rule__left_entity",
                "interaction_rule__right_entity",
            )
        )

    @staticmethod
    async def _get_owned_confirmed_episode(
        *,
        user_id: int,
        care_episode_id: int | None,
        connection,
    ) -> CareEpisode | None:
        if care_episode_id is None:
            return None
        episode = (
            await CareEpisode.filter(
                id=care_episode_id,
                user_id=user_id,
            )
            .using_db(connection)
            .first()
        )
        if episode is None or episode.confirmed_at is None or not episode.confirmation_hash:
            raise CareEpisodeNotFoundError
        return episode

    @staticmethod
    async def _get_or_create_session(
        *,
        user_id: int,
        episode: CareEpisode | None,
        requested_care_episode_id: int | None,
        conversation_id: int | None,
        connection,
    ) -> ChatSession:
        if conversation_id is None:
            return await ChatSession.create(
                user_id=user_id,
                care_episode=episode,
                status=ChatSessionStatus.ACTIVE,
                using_db=connection,
            )
        session = (
            await ChatSession.filter(
                id=conversation_id,
                user_id=user_id,
                status=ChatSessionStatus.ACTIVE,
                deleted_at__isnull=True,
            )
            .using_db(connection)
            .first()
        )
        if session is None:
            raise ChatSessionNotFoundError
        if requested_care_episode_id is not None and session.care_episode_id != requested_care_episode_id:
            raise ChatContextMismatchError
        return session

    @staticmethod
    def _chat_route(result: MedicationChatResult) -> ChatRouteType:
        route_mapping = {
            MedicationChatRoute.MEDICATION_GUIDE: ChatRouteType.PUBLIC_RAG,
            MedicationChatRoute.SUPPLEMENT_GUIDE: ChatRouteType.PUBLIC_RAG,
            MedicationChatRoute.ACTIVE_INTAKE: ChatRouteType.PATIENT_AND_PUBLIC,
            MedicationChatRoute.INTERACTION: ChatRouteType.INTERACTION,
            MedicationChatRoute.GENERAL_GUIDANCE: ChatRouteType.GENERAL_LIFESTYLE,
            MedicationChatRoute.CLARIFICATION: ChatRouteType.SAFETY_RESPONSE,
            MedicationChatRoute.RESTRICTED: ChatRouteType.SAFETY_RESPONSE,
        }
        return route_mapping[result.route]

    @staticmethod
    def _source_payload(source: MedicationChatSource) -> dict[str, object]:
        if source.kind == MedicationChatSourceKind.PATIENT_MEDICATION:
            return {
                "source_type": ChatSourceType.PATIENT_SAVED_FIELD,
                "patient_source_kind": PatientSourceKind.MEDICATION,
                "medication_id": source.medication_id,
            }
        if source.kind == MedicationChatSourceKind.PATIENT_SUPPLEMENT:
            return {
                "source_type": ChatSourceType.USER_SUPPLEMENT,
                "user_suppl_nutrient_id": source.user_supplement_id,
            }
        if source.kind == MedicationChatSourceKind.INTERACTION_RULE:
            return {
                "source_type": ChatSourceType.INTERACTION_RULE,
                "interaction_rule_id": source.interaction_rule_id,
            }
        if source.kind == MedicationChatSourceKind.MEDICATION_GUIDE:
            guide_key = str(source.medication_guide_id)
            return {
                "source_type": ChatSourceType.PUBLIC_RAG_CHUNK,
                "public_dataset_key": "MEDICATION_PRODUCT_GUIDE",
                "dataset_version": "rdbms-v1",
                "vector_chunk_id": f"medication-guide:{guide_key}",
                "source_record_key": guide_key,
                "source_title": source.title,
                "source_organization": source.organization,
                "source_url": source.url,
            }
        score = (
            max(Decimal("0"), Decimal(str(source.similarity_score))) if source.similarity_score is not None else None
        )
        return {
            "source_type": ChatSourceType.PUBLIC_RAG_CHUNK,
            "public_dataset_key": source.dataset_key,
            "dataset_version": source.dataset_version,
            "vector_chunk_id": source.vector_chunk_id,
            "source_record_key": source.vector_chunk_id,
            "source_title": source.title,
            "source_organization": source.organization,
            "source_url": source.url,
            "source_page_number": source.source_page_number,
            "similarity_score": score,
        }
