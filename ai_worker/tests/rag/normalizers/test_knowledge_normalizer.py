from ai_worker.rag.normalizers.knowledge_normalizer import (
    KnowledgeNormalizer,
    TextQualityStatus,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeMetadata,
    KnowledgePage,
)


def build_pages(*contents: str) -> list[KnowledgePage]:
    metadata = KnowledgeMetadata(
        source_id="kpicia_adverse_case_report",
        document_id="case-1",
        title="독사조신 복용 후 어지러움",
        provider="약학정보원",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.ADVERSE_CASE_REPORT,
        dataset_version="pilot-v1",
    )
    return [
        KnowledgePage(
            content=content,
            metadata=metadata,
            page_number=index,
        )
        for index, content in enumerate(contents, start=1)
    ]


def test_normalize_pages_removes_repeated_header_and_page_numbers() -> None:
    pages = build_pages(
        "대한약사회 환자안전약물관리본부\n환자 정보: 72세 남성\n1/3",
        "대한약사회 환자안전약물관리본부\n이상사례: 어지러움\n2/3",
        "대한약사회 환자안전약물관리본부\n평가 의견: 상당히 확실함\n3/3",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "대한약사회 환자안전약물관리본부" not in normalized[0].content
    assert "1/3" not in normalized[0].content
    assert normalized[0].content == "환자 정보: 72세 남성"
    assert normalized[2].content == "평가 의견: 상당히 확실함"


def test_assess_quality_requires_ocr_for_long_unspaced_text() -> None:
    report = KnowledgeNormalizer().assess_quality("인삼과와파린을함께복용하면출혈위험이증가할수있습니다" * 10)

    assert report.status == TextQualityStatus.OCR_REQUIRED
    assert "LONG_UNSPACED_RUN" in report.reason_codes


def test_assess_quality_passes_normal_korean_text() -> None:
    report = KnowledgeNormalizer().assess_quality(
        "비타민 B6는 단백질과 아미노산 이용에 필요합니다. "
        "섭취 후 손발 저림이 발생하면 전문가와 상담하세요. "
        "이 문서는 기능성 내용과 섭취 시 주의사항을 제공합니다."
    )

    assert report.status == TextQualityStatus.PASS
    assert report.reason_codes == []


def test_assess_pages_quality_uses_total_document_length() -> None:
    pages = build_pages(
        "환자 정보와 복용 의약품을 확인한 정상적인 첫 번째 페이지입니다.",
        "이상사례와 평가 의견을 설명한 정상적인 두 번째 페이지입니다.",
    )

    report = KnowledgeNormalizer().assess_pages_quality(pages)

    assert report.status == TextQualityStatus.PASS
    assert report.character_count > 60
