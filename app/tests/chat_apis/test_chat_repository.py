import pytest

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatMessageStatus,
    ChatSafetyStatus,
)
from app.models.users import User
from app.repositories.chat_repository import (
    ChatRepository,
    ChatRequestInProgressError,
    ChatRequestPayloadMismatchError,
)


async def create_user(user_id: int = 1) -> User:
    return await User.create(
        id=user_id,
        email=f"chat-{user_id}@example.com",
        hashed_password="hashed-password",
        name=f"채팅 사용자 {user_id}",
    )


def build_core_result() -> MedicationChatResult:
    return MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer=("공공자료 추가 설명\n- 제품 주의사항입니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."),
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                title="의약품 안전사용 안내",
                organization="식품의약품안전처",
                url="https://example.org/guide",
                dataset_key="MEDICATION_KNOWLEDGE",
                dataset_version="knowledge-baseline-v1",
                vector_chunk_id="point-1",
                source_page_number=1,
                similarity_score=0.82,
            )
        ],
        model_name="gpt-4o-mini",
        prompt_version="medication-chat-prompt-v1",
        schema_version="medication-chat-result-v1",
        context_hash="a" * 64,
    )


@pytest.mark.asyncio
async def test_accept_request_creates_ordered_user_and_pending_assistant_messages() -> None:
    user = await create_user()

    accepted = await ChatRepository().accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="마그네슘은 어떤 영양제인가요?",
    )

    assert accepted.user_message.sequence_no == 1
    assert accepted.user_message.role == ChatMessageRole.USER
    assert accepted.user_message.status == ChatMessageStatus.COMPLETED
    assert accepted.assistant_message.sequence_no == 2
    assert accepted.assistant_message.role == ChatMessageRole.ASSISTANT
    assert accepted.assistant_message.status == ChatMessageStatus.PENDING
    assert accepted.history == []


@pytest.mark.asyncio
async def test_complete_request_saves_sources_in_citation_order() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 주의사항을 알려줘",
    )

    completed = await repository.complete_request(
        assistant_message_id=accepted.assistant_message.id,
        result=build_core_result(),
        duration_ms=1234,
    )

    sources = await ChatMessageSource.filter(
        chat_message_id=completed.id,
    ).order_by("citation_order")
    assert completed.status == ChatMessageStatus.COMPLETED
    assert completed.safety_status == ChatSafetyStatus.SAFE
    assert completed.duration_ms == 1234
    assert [source.citation_order for source in sources] == [1]
    assert sources[0].vector_chunk_id == "point-1"


@pytest.mark.asyncio
async def test_fail_request_never_leaves_pending_message() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="오메가3 정보를 알려줘",
    )

    await repository.fail_request(
        assistant_message_id=accepted.assistant_message.id,
        error_code="CHAT_UPSTREAM_UNAVAILABLE",
        duration_ms=1200,
    )

    message = await ChatMessage.get(id=accepted.assistant_message.id)
    assert message.status == ChatMessageStatus.FAILED
    assert message.error_code == "CHAT_UPSTREAM_UNAVAILABLE"
    assert message.completed_at is not None


@pytest.mark.asyncio
async def test_accept_request_returns_last_ten_completed_messages_in_order() -> None:
    user = await create_user()
    repository = ChatRepository()
    first = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="00000000-0000-4000-8000-000000000000",
        content="첫 질문",
    )
    await repository.complete_request(
        assistant_message_id=first.assistant_message.id,
        result=build_core_result().model_copy(update={"request_id": "00000000-0000-4000-8000-000000000000"}),
        duration_ms=10,
    )
    for index in range(1, 6):
        accepted = await repository.accept_request(
            user_id=user.id,
            care_episode_id=None,
            conversation_id=first.session.id,
            request_id=f"00000000-0000-4000-8000-{index:012d}",
            content=f"질문 {index}",
        )
        await repository.complete_request(
            assistant_message_id=accepted.assistant_message.id,
            result=build_core_result().model_copy(
                update={
                    "request_id": f"00000000-0000-4000-8000-{index:012d}",
                    "answer": f"답변 {index}",
                }
            ),
            duration_ms=10,
        )

    latest = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=first.session.id,
        request_id="99999999-9999-4999-8999-999999999999",
        content="최신 질문",
    )

    assert len(latest.history) == 10
    assert latest.history[0].content == "질문 1"
    assert latest.history[-1].content == "답변 5"


@pytest.mark.asyncio
async def test_duplicate_completed_request_reuses_saved_message() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )
    completed = await repository.complete_request(
        assistant_message_id=accepted.assistant_message.id,
        result=build_core_result(),
        duration_ms=100,
    )

    reused = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=accepted.session.id,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )

    assert reused.reused_assistant_message is not None
    assert reused.reused_assistant_message.id == completed.id
    assert await ChatMessage.filter(chat_session=accepted.session).count() == 2


@pytest.mark.asyncio
async def test_duplicate_pending_request_is_rejected() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )

    with pytest.raises(ChatRequestInProgressError):
        await repository.accept_request(
            user_id=user.id,
            care_episode_id=None,
            conversation_id=accepted.session.id,
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            content="타이레놀 정보",
        )


@pytest.mark.asyncio
async def test_first_request_retry_without_conversation_id_reuses_session() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )
    completed = await repository.complete_request(
        assistant_message_id=accepted.assistant_message.id,
        result=build_core_result(),
        duration_ms=100,
    )

    reused = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )

    assert reused.session.id == accepted.session.id
    assert reused.reused_assistant_message.id == completed.id
    assert await ChatMessage.filter(chat_session_id=accepted.session.id).count() == 2


@pytest.mark.asyncio
async def test_failed_request_retry_without_conversation_id_reuses_session() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )
    await repository.fail_request(
        assistant_message_id=accepted.assistant_message.id,
        error_code="CHAT_PROCESSING_FAILED",
        duration_ms=100,
    )

    retried = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )

    assert retried.session.id == accepted.session.id
    assert retried.user_message.sequence_no == 3
    assert retried.assistant_message.sequence_no == 4
    assert await ChatSession.all().count() == 1
    assert await ChatMessage.filter(chat_session_id=accepted.session.id).count() == 4


@pytest.mark.asyncio
async def test_duplicate_request_id_with_different_question_is_rejected() -> None:
    user = await create_user()
    repository = ChatRepository()
    accepted = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="타이레놀 정보",
    )

    with pytest.raises(ChatRequestPayloadMismatchError):
        await repository.accept_request(
            user_id=user.id,
            care_episode_id=None,
            conversation_id=accepted.session.id,
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            content="이부프로펜 정보",
        )
