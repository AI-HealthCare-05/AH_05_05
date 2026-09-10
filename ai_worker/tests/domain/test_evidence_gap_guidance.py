from ai_worker.domain.evidence_gap_guidance import (
    EvidenceGapGuidanceBuilder,
    EvidenceGapSubject,
)


def test_interaction_gap_guidance_offers_official_routes_without_claiming_safety() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.INTERACTION,
        entity_names=["아스피린", "오메가3"],
    )

    assert "확인된 범위" in answer
    assert "일반 안내" in answer
    assert "알 수 없는 범위" in answer
    assert "공식 확인 경로" in answer
    assert "의료진·약사에게 확인할 내용" in answer
    assert "안내 한계" not in answer
    assert "의료 전문가의 진단이나 처방을 대신하지 않습니다" not in answer
    assert "의약품안전나라" in answer
    assert "식품안전나라" in answer
    assert "아스피린 ↔ 오메가3" in answer
    assert "안전한 조합" not in answer


def test_supplement_gap_guidance_does_not_invent_product_facts() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.SUPPLEMENT,
        entity_names=["오메가3"],
    )

    assert "식품안전나라" in answer
    assert "효능:" not in answer
    assert "복용법:" not in answer
    assert "용량:" not in answer
    assert "제품명·성분명·함량" in answer
