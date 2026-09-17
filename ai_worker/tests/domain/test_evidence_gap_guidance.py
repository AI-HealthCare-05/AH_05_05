from ai_worker.domain.evidence_gap_guidance import (
    EvidenceGapGuidanceBuilder,
    EvidenceGapSubject,
)


def test_interaction_gap_guidance_states_the_gap_and_one_official_path() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.INTERACTION,
        entity_names=["아스피린", "오메가3"],
    )

    assert answer == (
        "✉️ **안내사항**\n\n- 아스피린 ↔ 오메가3 관련 자료를 찾지 못했습니다.\n"
        "- 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다.\n\n"
        "📭 **공식 확인 경로**\n\n"
        "- 의약품은 의약품안전나라, 건강기능식품은 식품안전나라에서 확인할 수 있습니다."
    )
    assert "일반 안내" not in answer
    assert "알 수 없는 범위" not in answer
    assert "의료진·약사에게 확인할 내용" not in answer


def test_supplement_gap_guidance_names_the_official_source_without_product_facts() -> None:
    """확인처는 대상에 따라 코드가 정한다. 근거가 없을 때 제품 사실은 보태지 않는다."""

    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.SUPPLEMENT,
        entity_names=["오메가3"],
    )

    assert "식품안전나라" in answer
    assert "의약품안전나라" not in answer
    assert "효능:" not in answer
    assert "복용법:" not in answer
    assert "용량:" not in answer
    assert "제품명·성분명·함량" not in answer


def test_medication_gap_guidance_points_to_the_drug_authority() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.MEDICATION,
        entity_names=["타이레놀"],
    )

    assert "의약품안전나라" in answer
    assert "식품안전나라" not in answer


def test_unresolved_target_quotes_the_question_instead_of_a_generic_label() -> None:
    """대상을 인식하지 못해도 무엇을 찾지 못했는지는 남는다.

    질문에서 이름을 뽑아내면 코드가 대상을 판단하게 되므로 문장을 그대로 인용한다.
    """

    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.UNKNOWN,
        entity_names=[],
        question="노니 분말의 효능이 뭐야?",
    )

    assert "「노니 분말의 효능이 뭐야?」 관련 자료를 찾지 못했습니다." in answer
    assert "질문 대상" not in answer


def test_unresolved_target_falls_back_when_the_question_is_too_long() -> None:
    answer = EvidenceGapGuidanceBuilder().build(
        subject=EvidenceGapSubject.UNKNOWN,
        entity_names=[],
        question="제가 요즘 잠을 잘 못 자서 이것저것 알아보다가 들어본 생소한 이름의 원료가 있는데 효능이 궁금해요",
    )

    assert "질문 대상 관련 자료를 찾지 못했습니다." in answer


def test_every_gap_guidance_states_that_unconfirmed_is_not_safe() -> None:
    """근거를 찾지 못한 것을 안전하다는 뜻으로 읽히게 두지 않는다."""

    for subject in EvidenceGapSubject:
        answer = EvidenceGapGuidanceBuilder().build(subject=subject, entity_names=["오메가3"])
        assert "안전하다는 뜻은 아닙니다" in answer, subject
