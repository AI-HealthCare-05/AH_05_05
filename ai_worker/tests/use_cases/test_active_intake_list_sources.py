from datetime import date
from uuid import uuid4

from ai_worker.schemas.conversation_gate import ConversationIntent
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    MedicationChatRequest,
    MedicationChatSourceKind,
)
from ai_worker.use_cases.answer_medication_question import AnswerMedicationQuestionUseCase


def supplement(name: str, registration_id: int) -> ActiveSupplement:
    return ActiveSupplement(
        registration_id=registration_id,
        supplement_nutrient_id=registration_id,
        name=name,
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 9, 1),
    )


def test_registered_items_are_reported_as_sources() -> None:
    sources = AnswerMedicationQuestionUseCase._active_intake_sources(
        context=ActiveIntakeContext(user_id=1, supplements=[supplement("코랄칼슘", 7)]),
        intent=ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
    )

    assert [(item.kind, item.user_supplement_id) for item in sources] == [
        (MedicationChatSourceKind.PATIENT_SUPPLEMENT, 7)
    ]


def test_medication_list_reports_its_own_source_kind() -> None:
    sources = AnswerMedicationQuestionUseCase._active_intake_sources(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[ActiveMedication(medication_id=3, care_episode_id=1, name="와파린")],
        ),
        intent=ConversationIntent.ACTIVE_MEDICATION_LIST,
    )

    assert [(item.kind, item.medication_id) for item in sources] == [(MedicationChatSourceKind.PATIENT_MEDICATION, 3)]


def test_sources_match_what_the_answer_actually_lists() -> None:
    """합쳐 보인 항목의 출처가 둘로 나뉘면 근거 개수가 답변과 어긋난다."""
    sources = AnswerMedicationQuestionUseCase._active_intake_sources(
        context=ActiveIntakeContext(
            user_id=1,
            supplements=[supplement("비타 D 2000(120캡슐)", 1), supplement("비타 D 2000(60캡슐)", 2)],
        ),
        intent=ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
    )

    assert [item.title for item in sources] == ["사용자 복용 영양제 · 비타 D 2000"]


def test_the_list_answer_carries_the_sources_it_built() -> None:
    """출처를 만들어 두고 답변에 싣지 않으면 사용자에게는 근거가 없는 것과 같다."""
    context = ActiveIntakeContext(user_id=1, supplements=[supplement("코랄칼슘", 7)])

    result = AnswerMedicationQuestionUseCase._active_intake_list_result(
        request=MedicationChatRequest(request_id=uuid4(), user_id=1, question="내가 먹는 영양제 뭐야?"),
        context=context,
        intent=ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
    )

    assert "코랄칼슘" in result.answer
    assert [(item.kind, item.user_supplement_id) for item in result.sources] == [
        (MedicationChatSourceKind.PATIENT_SUPPLEMENT, 7)
    ]


def test_nothing_is_cited_when_no_item_is_listed() -> None:
    """`등록된 게 없습니다`라고 답하면서 근거를 제시하면 안 된다."""
    sources = AnswerMedicationQuestionUseCase._active_intake_sources(
        context=ActiveIntakeContext(user_id=1, supplements=[supplement("(120캡슐)", 1)]),
        intent=ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
    )

    assert sources == []
