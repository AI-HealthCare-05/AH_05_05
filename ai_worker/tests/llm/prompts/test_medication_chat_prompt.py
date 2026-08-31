from ai_worker.llm.prompts.medication_chat_prompt import SYSTEM_PROMPT


def test_system_prompt_requires_compact_plain_text_product_answer() -> None:
    assert "Markdown 기호" in SYSTEM_PROMPT
    assert "빈 항목은 출력하지" in SYSTEM_PROMPT
    assert "질문과 직접 관련된 핵심 항목" in SYSTEM_PROMPT


def test_system_prompt_limits_interaction_answer_to_matching_evidence() -> None:
    assert "두 질문 성분을 모두" in SYSTEM_PROMPT
    assert "근거에 없는 복용 간격·용량" in SYSTEM_PROMPT
    assert "동물·세포 연구" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_product_and_ingredient_family_evidence() -> None:
    assert "정확 제품의 RDBMS 안내를 우선" in SYSTEM_PROMPT
    assert "성분 계열 일반 정보" in SYSTEM_PROMPT
    assert "한국어로 핵심만 요약" in SYSTEM_PROMPT
    assert "근거가 없는 항목은 만들지" in SYSTEM_PROMPT
