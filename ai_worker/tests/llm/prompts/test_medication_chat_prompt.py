import json
from importlib import import_module

from ai_worker.llm.prompts.medication_chat_prompt import (
    MEDICATION_CHAT_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_medication_chat_messages,
)
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.evidence_reasoning import EvidenceClaim, EvidenceReasoningOutput
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSessionReference,
    MedicationChatSessionReferenceEntity,
    MedicationEvidenceCoverage,
)
from ai_worker.schemas.medication_search import MedicationQueryEntityType


def test_prompt_document_parser_extracts_runtime_sections() -> None:
    prompt_assets = import_module("ai_worker.llm.prompts.prompt_assets")
    parser = getattr(
        prompt_assets,
        "parse_prompt_template_document",
        None,
    )

    assert callable(parser)

    document = parser(
        """
<!-- prompt:system:start -->
시스템 지침
<!-- prompt:system:end -->
<!-- prompt:user:start -->
질문: {payload_json}
<!-- prompt:user:end -->
<!-- prompt:assistant_example:start -->
근거가 확인된 내용만 답변합니다.
<!-- prompt:assistant_example:end -->
"""
    )

    assert document.system == "시스템 지침"
    assert document.user == "질문: {payload_json}"
    assert document.assistant_example == ("근거가 확인된 내용만 답변합니다.")


def test_build_messages_applies_markdown_user_template() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀의 주의사항을 알려줘",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="주의사항: 확인된 초안입니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    assert user_content.startswith("입력 데이터(JSON)\n")
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["question"] == "타이레놀의 주의사항을 알려줘"
    assert payload["draft_answer"] == "주의사항: 확인된 초안입니다."


def test_build_messages_includes_only_structured_evidence_reasoning_result() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="마그네슘과 아연을 같이 먹어도 돼?",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="확인된 상호작용 초안입니다.",
        route=MedicationChatRoute.INTERACTION,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
        evidence_reasoning=EvidenceReasoningOutput(
            reasoning_status="SUPPORTED",
            interaction_decision="INTERACTION_CONFIRMED",
            claims=[
                EvidenceClaim(
                    section_type=KnowledgeSectionType.INTERACTION,
                    statement="두 성분의 직접 관계가 확인됐습니다.",
                    evidence_ids=["chunk:abc"],
                )
            ],
        ),
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["evidence_reasoning"] == {
        "reasoning_status": "SUPPORTED",
        "interaction_decision": "INTERACTION_CONFIRMED",
        "claims": [
            {
                "section_type": "INTERACTION",
                "statement": "두 성분의 직접 관계가 확인됐습니다.",
                "evidence_ids": ["chunk:abc"],
                "scope_note": None,
            }
        ],
        "supported_action": None,
        "missing_section_types": [],
        "conflict_evidence_ids": [],
    }


def test_build_messages_omits_unreferenced_history_from_general_question() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="마그네슘과 아연을 같이 먹어도 돼?",
        history=[
            ChatHistoryMessage(
                role=ChatRole.ASSISTANT,
                content="리바록사반은 임의로 중단하지 마세요.",
            )
        ],
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="마그네슘과 아연 관련 근거를 확인합니다.",
        route=MedicationChatRoute.INTERACTION,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["history"] == []
    assert "리바록사반" not in user_content


def test_build_messages_keeps_history_for_confirmed_session_reference() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="그 약의 복용법도 알려줘.",
        history=[
            ChatHistoryMessage(
                role=ChatRole.ASSISTANT,
                content="타이레놀정500밀리그람의 효능을 안내했습니다.",
            )
        ],
        session_reference=MedicationChatSessionReference(
            entities=[
                MedicationChatSessionReferenceEntity(
                    name="타이레놀정500밀리그람",
                    entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                    kind="DRUG",
                )
            ]
        ),
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="제품 복용법 초안입니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["history"] == [
        {
            "role": "ASSISTANT",
            "content": "타이레놀정500밀리그람의 효능을 안내했습니다.",
        }
    ]


def test_system_prompt_requires_limited_markdown_product_answer() -> None:
    assert "✅ **효능**" in SYSTEM_PROMPT
    assert "`- ` 목록" in SYSTEM_PROMPT
    assert "굵은 제품명만" in SYSTEM_PROMPT
    assert "값이 없는 항목은 출력하지" in SYSTEM_PROMPT
    assert "질문과 직접 관계있는 섹션" in SYSTEM_PROMPT


def test_system_prompt_uses_v7_six_element_contract_and_private_checklist() -> None:
    assert MEDICATION_CHAT_PROMPT_VERSION == "medication-chat-prompt-v7"
    for heading in (
        "역할(Role)",
        "작업(Task)",
        "내용(Content)",
        "형식(Format)",
        "제약(Constraint)",
        "예시(Example)",
    ):
        assert heading in SYSTEM_PROMPT
    assert "내부적으로 점검" in SYSTEM_PROMPT
    assert "점검 과정이나 숨겨진 추론문은 출력하지" in SYSTEM_PROMPT
    assert "covered section만 출력" in SYSTEM_PROMPT
    assert "초안에 포함된 의료 면책 문구를 유지" not in SYSTEM_PROMPT
    assert "✉️ **안내사항**" in SYSTEM_PROMPT
    assert "📭 **공식 확인 경로**" in SYSTEM_PROMPT
    assert "의료진·약사에게 확인할 내용" not in SYSTEM_PROMPT


def test_system_prompt_forbids_repeating_unverified_interaction_notice() -> None:
    assert "확인하지 못한 조합은 한 번만 표시" in SYSTEM_PROMPT


def test_system_prompt_limits_each_requested_section_to_short_bullets() -> None:
    assert "각 bullet은 한 가지 핵심만 약 70자 이내" in SYSTEM_PROMPT
    assert "섹션당 최대 4개" in SYSTEM_PROMPT


def test_prompt_limits_product_output_to_requested_sections() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀은 어디에 좋고 먹을 때 뭘 조심해야 해?",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="효능과 주의사항이 포함된 공식 제품 안내입니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
            covered_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
        ),
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["requested_section_types"] == ["FUNCTION", "CAUTION"]
    assert "covered section만 출력" in SYSTEM_PROMPT


def test_system_prompt_treats_active_intake_as_requested_sections() -> None:
    assert "💊 **복약정보**" in SYSTEM_PROMPT
    assert "💪🏻 **영양제 정보**" in SYSTEM_PROMPT
    assert "active_supplement_names" in SYSTEM_PROMPT


def test_system_prompt_requires_server_selected_active_medication_section() -> None:
    assert "show_active_medication_section" in SYSTEM_PROMPT
    assert "active_medication_names" in SYSTEM_PROMPT


def test_build_messages_marks_active_medication_section_as_required_for_medication_route() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀의 효능을 알려줘",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="💊 **복약정보**\n- 세레콕시브캡슐200mg\n\n타이레놀 안내",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="세레콕시브캡슐200mg",
                )
            ],
        ),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["show_active_medication_section"] is True


def test_build_messages_does_not_require_active_medication_section_for_general_route() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="안녕하세요",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="안녕하세요.",
        route=MedicationChatRoute.GENERAL_GUIDANCE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="세레콕시브캡슐200mg",
                )
            ],
        ),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["show_active_medication_section"] is False


def test_build_messages_redacts_unrequested_dosage_from_draft() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀은 어디에 좋고 먹을 때 뭘 조심해야 해?",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="주의사항: 일일최대용량(4|000mg)을 초과하여 복용하지 마십시오.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
            covered_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
        ),
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert "4|000mg" not in payload["draft_answer"]
    assert "[용량 정보 생략]" in payload["draft_answer"]


def test_build_messages_keeps_requested_dosage_in_draft() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="마그오캡슐500mg의 복용법을 알려줘",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="사용법: 1일 1~2캡슐을 나누어 복용합니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.DAILY_INTAKE],
            covered_section_types=[KnowledgeSectionType.DAILY_INTAKE],
        ),
    )

    messages = build_medication_chat_messages(
        request=request,
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    user_content = messages[-1].content
    assert isinstance(user_content, str)
    payload = json.loads(user_content.removeprefix("입력 데이터(JSON)\n"))
    assert payload["draft_answer"] == "사용법: 1일 1~2캡슐을 나누어 복용합니다."


def test_system_prompt_limits_interaction_answer_to_matching_evidence() -> None:
    assert "검증된 evidence claims" in SYSTEM_PROMPT
    assert "의료 사실·수치·행동 지침은 초안 또는 검증된 claim 범위" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_product_and_ingredient_family_evidence() -> None:
    assert "서버가 제공한 입력과 후보를 사실의 경계" in SYSTEM_PROMPT
    assert "입력에 직접 근거가 없는 의료 사실은 확정하지" in SYSTEM_PROMPT
