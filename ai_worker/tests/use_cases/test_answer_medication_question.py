from datetime import date

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    InteractionRuleFact,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationGuideFact,
    MedicationGuideLookup,
)
from ai_worker.use_cases.answer_medication_question import (
    AnswerMedicationQuestionUseCase,
)


class FakeContextProvider:
    def __init__(self, context: ActiveIntakeContext) -> None:
        self.context = context

    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext:
        return self.context


class FakeGuideRepository:
    def __init__(self, lookup: MedicationGuideLookup) -> None:
        self.lookup = lookup

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        return self.lookup


class ExactNameGuideRepository:
    def __init__(
        self,
        *,
        expected_name: str,
        lookup: MedicationGuideLookup,
    ) -> None:
        self.expected_name = expected_name
        self.lookup = lookup

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        if product_name == self.expected_name:
            return self.lookup
        return MedicationGuideLookup()


class UnexpectedGuideRepository:
    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        raise AssertionError(f"영양제 상호작용 질문에서 의약품 제품 조회를 호출했습니다: {product_name}")


class FakeRuleRepository:
    def __init__(self, rules: list[InteractionRuleFact]) -> None:
        self.rules = rules

    async def find_approved_rules(
        self,
        *,
        context: ActiveIntakeContext,
    ) -> list[InteractionRuleFact]:
        return self.rules


class FakeKnowledgeRetriever:
    def __init__(
        self,
        chunks: list[RetrievedKnowledgeChunk] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.error = error

    async def search(
        self,
        *,
        question: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        if self.error is not None:
            raise self.error
        return self.chunks


class PassthroughGenerator:
    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        return result


class PassthroughValidator:
    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        return result


def build_request(
    question: str,
    *,
    care_episode_id: int | None = None,
) -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        care_episode_id=care_episode_id,
        question=question,
    )


def build_guide() -> MedicationGuideFact:
    return MedicationGuideFact(
        medication_guide_id=12,
        item_seq="100",
        product_name="타이레놀정500밀리그람",
        manufacturer_name="테스트제약",
        efficacy="통증과 발열을 완화합니다.",
        usage_instructions="제품 설명서와 전문가의 안내를 따릅니다.",
        pre_use_warning="성분을 확인합니다.",
        precautions="정해진 용법을 지킵니다.",
        drug_food_interactions="다른 약 복용 시 전문가에게 알립니다.",
        adverse_reactions="이상반응이 있으면 전문가와 상담합니다.",
        storage_instructions="실온에 보관합니다.",
    )


def build_chunk() -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="point-1",
        chunk_id="a" * 64,
        content="아세트아미노펜 복용 시 제품별 함량과 주의사항을 확인합니다.",
        embedding_text="아세트아미노펜 주의사항",
        token_count=20,
        similarity_score=0.82,
        metadata=KnowledgeChunkMetadata(
            source_id="MFDS",
            document_id="drug-guide-1",
            title="의약품 안전사용 안내",
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
            dataset_version="knowledge-baseline-v1",
            section_type=KnowledgeSectionType.CAUTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


def build_use_case(
    *,
    context: ActiveIntakeContext | None = None,
    lookup: MedicationGuideLookup | None = None,
    rules: list[InteractionRuleFact] | None = None,
    retriever: FakeKnowledgeRetriever | None = None,
) -> AnswerMedicationQuestionUseCase:
    return AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(context or ActiveIntakeContext(user_id=1)),
        guide_repository=FakeGuideRepository(lookup or MedicationGuideLookup()),
        interaction_rule_repository=FakeRuleRepository(rules or []),
        knowledge_retriever=retriever or FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )


async def test_general_drug_question_runs_without_episode() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
    ).execute(
        build_request("타이레놀정500밀리그람은 어떤 약인가요?"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer
    assert "성분을 확인합니다" in result.answer
    assert "다른 약 복용 시 전문가에게 알립니다" in result.answer


async def test_confirmed_medication_precedes_general_guide_and_rag() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="타이레놀정500밀리그람",
                dose="1정",
                times_per_day=3,
                days=3,
                prescribed_at=date(2026, 8, 25),
            )
        ],
    )
    result = await build_use_case(
        context=context,
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[build_chunk()]),
    ).execute(
        build_request(
            "이 약을 어떻게 먹어야 하나요?",
            care_episode_id=100,
        )
    )

    assert result.answer.index("사용자 확정 복약정보") < result.answer.index("일반 제품 안내")
    assert result.answer.index("일반 제품 안내") < result.answer.index("공공자료 추가 설명")


async def test_no_interaction_evidence_never_claims_safe() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="아스피린",
            )
        ],
    )
    result = await build_use_case(context=context).execute(
        build_request("아스피린과 오메가3를 같이 먹어도 괜찮나요?"),
    )

    assert result.route == MedicationChatRoute.INTERACTION
    assert "안전합니다" not in result.answer
    assert "확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다" in result.answer


async def test_qdrant_failure_falls_back_to_rdbms_facts() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="타이레놀정500밀리그람",
                dose="1정",
            )
        ],
    )
    result = await build_use_case(
        context=context,
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(error=RuntimeError("qdrant down")),
    ).execute(
        build_request("타이레놀정500밀리그람 주의사항을 알려줘", care_episode_id=100),
    )

    assert "사용자 확정 복약정보" in result.answer
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "RAG_UNAVAILABLE" in result.safety_reason_codes


async def test_ambiguous_medication_name_requests_clarification() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            candidate_names=[
                "타이레놀정500밀리그람",
                "타이레놀8시간이알서방정",
            ],
        ),
    ).execute(build_request("타이레놀은 한 번에 몇 정 먹나요?"))

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert "제품명을 확인" in result.answer


async def test_general_brand_name_uses_reference_efficacy_without_guessing_dose() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            representative_guide=build_guide(),
            candidate_names=[
                "타이레놀정500밀리그람",
                "타이레놀8시간이알서방정",
            ],
        ),
    ).execute(
        build_request(
            "타이레놀의 효능과 복용 시 주의사항을 알려줘.",
        )
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer
    assert "제품별 성분·함량·제형" in result.answer
    assert "제품 설명서와 전문가의 안내를 따릅니다" not in result.answer


async def test_general_brand_name_removes_possessive_particle_before_lookup() -> None:
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(
            ActiveIntakeContext(user_id=1),
        ),
        guide_repository=ExactNameGuideRepository(
            expected_name="타이레놀",
            lookup=MedicationGuideLookup(
                is_ambiguous=True,
                representative_guide=build_guide(),
                candidate_names=[
                    "타이레놀정500밀리그람",
                    "타이레놀8시간이알서방정",
                ],
            ),
        ),
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )

    result = await use_case.execute(
        build_request(
            "타이레놀의 효능과 복용 시 주의사항을 알려줘.",
        )
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer


async def test_supplement_evidence_prevents_partial_drug_name_clarification() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            )
        }
    )
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            candidate_names=["마그밀정", "산화마그네슘정"],
        ),
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
    ).execute(build_request("마그네슘은 왜 먹어?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "제품명을 확인" not in result.answer
    assert "공공자료 추가 설명" in result.answer


async def test_supplement_evidence_precedes_single_partial_medication_match() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": ("마그네슘은 에너지 이용과 신경·근육 기능 유지에 필요합니다."),
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
    ).execute(build_request("마그네슘은 왜 먹어?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "에너지 이용" in result.answer
    assert "일반 제품 안내" not in result.answer
    assert all(source.medication_guide_id is None for source in result.sources)


async def test_supplement_pair_question_skips_medication_product_lookup() -> None:
    interaction_chunk = build_chunk().model_copy(
        update={
            "content": ("Supplemental zinc lowered measures of iron status in young women with low iron reserves."),
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "title": "Supplemental Zinc Lowers Measures of Iron Status",
                    "document_type": KnowledgeDocumentType.RESEARCH_ARTICLE,
                    "ingredient_names": ["아연", "철분"],
                    "section_type": KnowledgeSectionType.SUMMARY,
                }
            ),
        }
    )
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(ActiveIntakeContext(user_id=1)),
        guide_repository=UnexpectedGuideRepository(),
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(chunks=[interaction_chunk]),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )

    result = await use_case.execute(
        build_request("철분이 부족한 사람이 아연 영양제를 먹어도 되나요?"),
    )

    assert result.route == MedicationChatRoute.INTERACTION
    assert "검색된 상호작용 연구 근거" in result.answer
    assert "제품명을 확인" not in result.answer


def test_product_name_candidates_are_bounded_for_long_questions() -> None:
    candidates = AnswerMedicationQuestionUseCase._product_name_candidates(
        " ".join(f"후보{index}" for index in range(100)),
        context=ActiveIntakeContext(user_id=1),
    )

    assert len(candidates) <= 12


def test_this_medicine_does_not_choose_between_multiple_active_medications() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=100,
                name="아스피린",
            ),
            ActiveMedication(
                medication_id=2,
                care_episode_id=100,
                name="타이레놀",
            ),
        ],
    )

    candidates = AnswerMedicationQuestionUseCase._product_name_candidates(
        "이 약은 어떻게 먹어?",
        context=context,
    )

    assert "아스피린" not in candidates
    assert "타이레놀" not in candidates
