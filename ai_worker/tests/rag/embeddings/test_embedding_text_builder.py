from ai_worker.rag.embeddings.embedding_text_builder import (
    build_medical_retrieval_query_text,
    sanitize_embedding_content,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


def test_sanitize_embedding_content_removes_layout_noise_without_losing_medical_terms() -> None:
    source = (
        "\ufeff  12  \n\n타이레놀정500mg (아세트아미노펜)\u200b  \n\n"
        "하루 4,000mg을 초과하지 마세요.  \n\n"
        "표 | 1회 | 500mg  "
    )

    sanitized = sanitize_embedding_content(source)

    assert "\ufeff" not in sanitized
    assert "\u200b" not in sanitized
    assert "타이레놀정500mg (아세트아미노펜)" in sanitized
    assert "4,000mg" in sanitized
    assert "표\n1회\n500mg" in sanitized
    assert not sanitized.startswith("12")


def test_build_query_text_keeps_question_and_adds_only_resolved_search_structure() -> None:
    query = build_medical_retrieval_query_text(
        question="타이레놀과 비타민 D 같이 먹어도 돼?",
        entity_names=["아세트아미노펜", "비타민 D"],
        section_types=[KnowledgeSectionType.INTERACTION],
        pair_names=["아세트아미노펜-비타민 D"],
    )

    assert query.splitlines()[0] == "[질문] 타이레놀과 비타민 D 같이 먹어도 돼?"
    assert "[대상] 아세트아미노펜, 비타민 D" in query
    assert "[요청 섹션] INTERACTION" in query
    assert "[상호작용 조합] 아세트아미노펜-비타민 D" in query
