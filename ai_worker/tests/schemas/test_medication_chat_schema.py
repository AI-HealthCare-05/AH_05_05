from datetime import date

import pytest
from pydantic import ValidationError

from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)


def test_general_drug_question_accepts_missing_care_episode() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        care_episode_id=None,
        question=" 타이레놀은 어떤 약인가요? ",
        history=[
            ChatHistoryMessage(
                role=ChatRole.USER,
                content="해열진통제가 궁금해요.",
            )
        ],
    )

    assert request.care_episode_id is None
    assert request.question == "타이레놀은 어떤 약인가요?"


def test_medication_chat_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError, match="string_too_short"):
        MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="  ",
        )


def test_active_intake_context_preserves_confirmed_medication() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="아스피린",
                dose="1정",
                times_per_day=1,
                days=7,
                prescribed_at=date(2026, 8, 25),
            )
        ],
    )

    assert context.medications[0].name == "아스피린"
    assert context.medications[0].care_episode_id == 100


def test_medication_chat_result_keeps_grounded_source_identifiers() -> None:
    result = MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer="확인된 제품 안내를 설명드립니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                title="e약은요 · 제품 사용 안내",
                medication_guide_id=12,
                organization="식품의약품안전처",
            )
        ],
        prompt_version="medication-chat-v1",
        schema_version="medication-chat-result-v1",
    )

    assert result.sources[0].medication_guide_id == 12
    assert result.sources[0].kind == MedicationChatSourceKind.MEDICATION_GUIDE
