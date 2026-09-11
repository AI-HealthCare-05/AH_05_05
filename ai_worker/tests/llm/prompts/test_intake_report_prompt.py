import json

from ai_worker.llm.prompts.intake_report_prompt import (
    INTAKE_REPORT_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_intake_report_messages,
)
from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportExecutiveSummary,
    IntakeReportNutrientTotal,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import MedicationGuideFact


def _guide() -> MedicationGuideFact:
    return MedicationGuideFact(
        medication_guide_id=91,
        item_seq="200001",
        product_name="등록 약 A",
        manufacturer_name="제조사 A",
        efficacy="확인된 효능 원문",
        usage_instructions="1회 1정",
        pre_use_warning="임신 마지막 3개월에는 복용 전 확인",
        precautions="출혈 징후를 관찰",
        drug_food_interactions="음식 상호작용 자료 없음",
        adverse_reactions="위장 불편",
        storage_instructions="실온 보관",
    )


def test_runtime_prompt_uses_restored_v11_structure_and_current_input_contract() -> None:
    """Guard the restored v11 contract, not the quality of an uncalled live model."""
    assert INTAKE_REPORT_PROMPT_VERSION == "intake-report-prompt-v11"
    for instruction in (
        "v11 문장 스타일",
        "전체를 자연스러운 해요체로 통일",
        "## 영양제끼리 확인할 점",
        "### 흡수를 돕는 조합",
        "### 흡수를 방해하는 조합",
        "**어떤 약인가요?**",
        "**주의하세요**",
        "**먹으면 안 돼요**",
        "약 N개·영양제 S개·조합 K개·영양소 M행",
        "현재 서버 입력 연결",
        "guide_evidence",
        "knowledge_evidence",
        "drug_food_interactions",
    ):
        assert instruction in SYSTEM_PROMPT


def _chunk() -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="point-1",
        chunk_id="a" * 64,
        content="12주 동안 성인을 관찰한 연구이며 인과관계를 확정할 수 없습니다.",
        embedding_text="성인 연구 12주",
        token_count=12,
        similarity_score=0.82,
        metadata=KnowledgeChunkMetadata(
            source_id="source-1",
            document_id="document-1",
            title="영양 성분 연구",
            provider="공개 연구기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version="dataset-v1",
            source_url="https://evidence.example/study-1",
            section_type=KnowledgeSectionType.RESULTS,
            page_start=2,
            page_end=2,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


def test_prompt_payload_preserves_all_database_rag_and_nutrient_evidence() -> None:
    """Would fail if the model sees summaries but not the source evidence or numeric basis."""
    draft = IntakeReportDraft(
        data_availability=IntakeReportDataAvailability(
            active_medication_count=1,
            rag_evidence_available=True,
        ),
        executive_summary=IntakeReportExecutiveSummary(summary="근거 기반 요약"),
        nutrient_totals=[
            IntakeReportNutrientTotal(
                nutrient_name="칼슘",
                daily_total="300 mg",
                calculation_status="AVAILABLE",
                amount="300",
                unit="mg",
                reference_value="650",
                reference_kind="RNI",
                reference_percent="46.15",
            )
        ],
        chart_data=IntakeReportChartData(medication_count=1),
        deterministic_markdown="# 약·영양제 생활관리 보고서\n\n근거 기반 초안",
        guide_evidence=[_guide()],
        knowledge_evidence=[_chunk()],
        profile_label="여자 · 30-49세",
        basis_note="제품 안내량 기준이며 실제 섭취량 합계가 아닙니다.",
    )

    message = build_intake_report_messages(draft=draft)[1].content
    payload = json.loads(message[message.index("{") : message.rindex("}") + 1])

    assert payload["guide_evidence"][0]["efficacy"] == "확인된 효능 원문"
    assert payload["knowledge_evidence"][0]["content"].startswith("12주 동안")
    assert payload["nutrient_totals"][0]["reference_percent"] == "46.15"
    assert payload["profile_label"] == "여자 · 30-49세"
    assert payload["basis_note"].startswith("제품 안내량 기준")
