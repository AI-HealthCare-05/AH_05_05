import pytest

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_chat import (
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from ai_worker.schemas.medication_search import MedicationQueryEntityType
from app.models.care import CareEpisode
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatMessageStatus,
    ChatSafetyStatus,
)
from app.models.interactions import MedicationProductGuide
from app.models.medications import Medication
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import User
from app.repositories.chat_repository import (
    ChatRepository,
    ChatRequestInProgressError,
    ChatRequestPayloadMismatchError,
)

TRACE_ID = "11111111-1111-4111-8111-111111111111"


async def create_user(user_id: int = 1) -> User:
    return await User.create(
        id=user_id,
        email=f"chat-{user_id}@example.com",
        hashed_password="hashed-password",
        name=f"채팅 사용자 {user_id}",
    )


async def create_medication_guide() -> MedicationProductGuide:
    return await MedicationProductGuide.create(
        item_seq="199900000",
        product_name="타이레놀산500밀리그램(아세트아미노펜)",
        manufacturer_name="테스트제약",
        efficacy="통증과 발열 완화",
        usage_instructions="용법용량",
        pre_use_warning="사용 전 주의사항",
        precautions="주의사항",
        drug_food_interactions="음식 상호작용",
        adverse_reactions="이상반응",
        storage_instructions="보관방법",
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
        langsmith_trace_id=TRACE_ID,
    )

    sources = await ChatMessageSource.filter(
        chat_message_id=completed.id,
    ).order_by("citation_order")
    assert completed.status == ChatMessageStatus.COMPLETED
    assert completed.safety_status == ChatSafetyStatus.SAFE
    assert completed.duration_ms == 1234
    assert completed.langsmith_trace_id == TRACE_ID
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
        langsmith_trace_id=TRACE_ID,
    )

    message = await ChatMessage.get(id=accepted.assistant_message.id)
    assert message.status == ChatMessageStatus.FAILED
    assert message.error_code == "CHAT_UPSTREAM_UNAVAILABLE"
    assert message.langsmith_trace_id == TRACE_ID
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
async def test_accept_request_recovers_drug_reference_from_prior_guide_source() -> None:
    user = await create_user()
    guide = await create_medication_guide()
    repository = ChatRepository()
    first = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="30000000-0000-4000-8000-000000000001",
        content="타이레놀은 어디에 좋고 무엇을 조심해야 하나요?",
    )
    await repository.complete_request(
        assistant_message_id=first.assistant_message.id,
        result=build_core_result().model_copy(
            update={
                "request_id": "30000000-0000-4000-8000-000000000001",
                "answer": "효능: 타이레놀은 통증과 발열 완화에 사용됩니다.",
                "sources": [
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                        title="e약은요 · 타이레놀산500밀리그램(아세트아미노펜)",
                        organization="식품의약품안전처",
                        medication_guide_id=guide.id,
                    ),
                ],
            },
        ),
        duration_ms=10,
    )

    next_request = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=first.session.id,
        request_id="30000000-0000-4000-8000-000000000002",
        content="그 약의 복용법도 알려줘.",
    )

    assert next_request.session_reference.entities[0].name == "타이레놀산500밀리그램(아세트아미노펜)"
    assert next_request.session_reference.entities[0].entity_type == MedicationQueryEntityType.PRODUCT_NAME
    assert next_request.session_reference.entities[0].kind == InteractionEntityKind.DRUG


@pytest.mark.asyncio
async def test_accept_request_recovers_typed_registered_intake_references_from_latest_session_answer() -> None:
    user = await create_user()
    episode = await CareEpisode.create(user=user)
    medication = await Medication.create(care_episode=episode, name="와파린")
    supplement = await UserSupplementNutrient.create(
        user=user,
        supplement_nutrient_id=None,
        custom_name="비타민 K",
        dose_amount="1.000",
        dose_unit="정",
        start_date="2026-09-09",
    )
    repository = ChatRepository()
    first = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="31000000-0000-4000-8000-000000000001",
        content="현재 복용 중인 약과 영양제를 정리해줘.",
    )
    await repository.complete_request(
        assistant_message_id=first.assistant_message.id,
        result=build_core_result().model_copy(
            update={
                "request_id": "31000000-0000-4000-8000-000000000001",
                "answer": "복약정보\n- 와파린\n\n영양제 정보\n- 비타민 K",
                "sources": [
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                        title="사용자 복용 약 · 와파린",
                        medication_id=medication.id,
                        care_episode_id=episode.id,
                    ),
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.PATIENT_SUPPLEMENT,
                        title="사용자 복용 영양제 · 비타민 K",
                        user_supplement_id=supplement.id,
                    ),
                ],
            },
        ),
        duration_ms=10,
    )

    next_request = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=first.session.id,
        request_id="31000000-0000-4000-8000-000000000002",
        content="그중 혈액 응고와 관련된 약은 무엇을 조심해야 해?",
    )

    assert [(entity.name, entity.entity_type, entity.kind) for entity in next_request.session_reference.entities] == [
        ("와파린", MedicationQueryEntityType.INGREDIENT_NAME, InteractionEntityKind.DRUG),
        ("비타민 K", MedicationQueryEntityType.INGREDIENT_NAME, InteractionEntityKind.SUPPLEMENT),
    ]


@pytest.mark.asyncio
async def test_accept_request_does_not_recover_registered_intake_reference_from_another_session() -> None:
    user = await create_user()
    episode = await CareEpisode.create(user=user)
    medication = await Medication.create(care_episode=episode, name="와파린")
    repository = ChatRepository()
    first = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="32000000-0000-4000-8000-000000000001",
        content="현재 복용 중인 약을 정리해줘.",
    )
    await repository.complete_request(
        assistant_message_id=first.assistant_message.id,
        result=build_core_result().model_copy(
            update={
                "request_id": "32000000-0000-4000-8000-000000000001",
                "sources": [
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                        title="사용자 복용 약 · 와파린",
                        medication_id=medication.id,
                        care_episode_id=episode.id,
                    ),
                ],
            },
        ),
        duration_ms=10,
    )

    new_session_request = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="32000000-0000-4000-8000-000000000002",
        content="그 약의 복용법을 알려줘.",
    )

    assert new_session_request.session_reference.entities == []


@pytest.mark.asyncio
async def test_accept_request_history_excludes_messages_from_another_session() -> None:
    user = await create_user()
    repository = ChatRepository()
    first_session = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="10000000-0000-4000-8000-000000000001",
        content="첫 세션 질문",
    )
    await repository.complete_request(
        assistant_message_id=first_session.assistant_message.id,
        result=build_core_result().model_copy(
            update={
                "request_id": "10000000-0000-4000-8000-000000000001",
                "answer": "일반 제품 안내\n- 제품: 세션A약 (테스트제약)",
            }
        ),
        duration_ms=10,
    )
    other_session = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=None,
        request_id="20000000-0000-4000-8000-000000000002",
        content="다른 세션 질문",
    )
    await repository.complete_request(
        assistant_message_id=other_session.assistant_message.id,
        result=build_core_result().model_copy(
            update={
                "request_id": "20000000-0000-4000-8000-000000000002",
                "answer": "일반 제품 안내\n- 제품: 세션B약 (테스트제약)",
            }
        ),
        duration_ms=10,
    )

    next_request = await repository.accept_request(
        user_id=user.id,
        care_episode_id=None,
        conversation_id=first_session.session.id,
        request_id="30000000-0000-4000-8000-000000000003",
        content="그 약의 복용법도 알려줘",
    )

    history_contents = [message.content for message in next_request.history]
    assert "일반 제품 안내\n- 제품: 세션A약 (테스트제약)" in history_contents
    assert "일반 제품 안내\n- 제품: 세션B약 (테스트제약)" not in history_contents


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
