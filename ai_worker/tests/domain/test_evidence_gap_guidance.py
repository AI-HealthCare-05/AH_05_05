from ai_worker.domain.evidence_gap_guidance import (
    EvidenceGapGuidanceBuilder,
    EvidenceGapSubject,
)


def test_interaction_gap_guidance_is_limited_to_notice_and_official_routes() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.INTERACTION,
        entity_names=["아스피린", "오메가3"],
    )

    assert answer == (
        "✉️ **안내사항**\n\n"
        "- 아스피린 ↔ 오메가3 관련 자료를 찾지 못했습니다.\n\n"
        "📭 **공식 확인 경로**\n\n"
        "- 의약품은 의약품안전나라에서 제품명 또는 성분명을 확인하세요.\n"
        "- 영양제는 식품안전나라에서 건강기능식품 또는 기능성 원료 정보를 확인하세요."
    )
    assert "의료 전문가의 진단이나 처방을 대신하지 않습니다" not in answer
    assert "일반 안내" not in answer
    assert "알 수 없는 범위" not in answer
    assert "의료진·약사에게 확인할 내용" not in answer


def test_supplement_gap_guidance_does_not_invent_product_facts() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.SUPPLEMENT,
        entity_names=["오메가3"],
    )

    assert "식품안전나라" in answer
    assert "효능:" not in answer
    assert "복용법:" not in answer
    assert "용량:" not in answer
    assert "제품명·성분명·함량" not in answer
