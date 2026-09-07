from dataclasses import FrozenInstanceError
from typing import cast
from uuid import uuid4

import pytest

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)
from ai_worker.use_cases.medication_chat_pipeline import (
    MedicationChatDraft,
    PreparedMedicationQuestion,
)


def test_prepared_question_keeps_the_resolved_request_as_an_immutable_stage_output() -> None:
    prepared = PreparedMedicationQuestion(
        request=MedicationChatRequest(
            request_id=uuid4(),
            user_id=1,
            question="타이레놀은 어떤 약인가요?",
        ),
        resolution=None,
        early_result=None,
    )

    assert prepared.question_for_planning == "타이레놀은 어떤 약인가요?"
    with pytest.raises(FrozenInstanceError):
        prepared.request = cast(MedicationChatRequest, object())  # type: ignore[misc]


def test_draft_stage_marks_that_safety_validation_must_follow_llm_rewrite() -> None:
    draft = MedicationChatDraft(
        result=MedicationChatResult(
            request_id=uuid4(),
            answer="근거 기반 초안",
            route=MedicationChatRoute.MEDICATION_GUIDE,
            safety_status=SafetyStatus.SAFE,
            prompt_version="test",
            schema_version="test",
        ),
        resolution=None,
    )

    assert draft.safety_validation_required is True
