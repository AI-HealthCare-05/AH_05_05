import json
from importlib import import_module

from ai_worker.llm.prompts.medication_chat_prompt import (
    MEDICATION_CHAT_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_medication_chat_messages,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationEvidenceCoverage,
)


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


def test_system_prompt_requires_limited_markdown_product_answer() -> None:
    assert "✅ **효능**" in SYSTEM_PROMPT
    assert "`- ` 목록" in SYSTEM_PROMPT
    assert "# 제목" in SYSTEM_PROMPT
    assert "빈 항목은 출력하지" in SYSTEM_PROMPT
    assert "질문과 직접 관계있는 정보만" in SYSTEM_PROMPT


def test_system_prompt_uses_v6_few_shot_and_private_answer_checklist() -> None:
    assert MEDICATION_CHAT_PROMPT_VERSION == "medication-chat-prompt-v6"
    assert "Few-shot" in SYSTEM_PROMPT
    assert "내부 점검" in SYSTEM_PROMPT
    assert "최종 답변에는 내부 점검 과정" in SYSTEM_PROMPT
    assert "포함된 섹션만 출력" in SYSTEM_PROMPT
    assert "초안에 포함된 의료 면책 문구를 유지" not in SYSTEM_PROMPT
    assert "✉️ **안내사항**" in SYSTEM_PROMPT
    assert "📭 **공식 확인 경로**" in SYSTEM_PROMPT
    assert "의료진·약사에게 확인할 내용" not in SYSTEM_PROMPT


def test_system_prompt_limits_each_requested_section_to_short_bullets() -> None:
    assert "한 bullet은 약 70자 이내" in SYSTEM_PROMPT
    assert "섹션당 핵심 bullet 한 개" in SYSTEM_PROMPT


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
    assert "DAILY_INTAKE가 요청되지 않았다면" in SYSTEM_PROMPT


def test_system_prompt_treats_active_intake_as_requested_sections() -> None:
    assert "📋 **복약정보**" in SYSTEM_PROMPT
    assert "💊 **영양제 정보**" in SYSTEM_PROMPT
    assert "등록한 복약정보" in SYSTEM_PROMPT


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
    assert "두 질문 성분을 모두" in SYSTEM_PROMPT
    assert "근거에 없는 복용 간격·용량" in SYSTEM_PROMPT
    assert "동물·세포 연구" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_product_and_ingredient_family_evidence() -> None:
    assert "정확 제품의 RDBMS 안내를 우선" in SYSTEM_PROMPT
    assert "성분 계열 일반 정보" in SYSTEM_PROMPT
    assert "한국어로 핵심만 요약" in SYSTEM_PROMPT
    assert "근거가 없는 항목은 만들지" in SYSTEM_PROMPT
