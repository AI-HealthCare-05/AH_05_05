import hashlib
import json
import re

from ai_worker.domain.interfaces import (
    ActiveIntakeContextProvider,
    GroundedClaimValidator,
    InteractionRuleRepository,
    MedicationAnswerGenerator,
    MedicationGuideRepository,
    MedicationKnowledgeRetriever,
)
from ai_worker.llm.assemblers.medication_answer_assembler import (
    MedicationAnswerAssembler,
)
from ai_worker.rag.metadata.supplement_interaction_registry import (
    find_supplement_interaction_pair,
    known_supplement_names_in,
    supplement_pair_matches_text,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
    MedicationGuideLookup,
)

MEDICATION_CHAT_PROMPT_VERSION = "medication-chat-prompt-v2"
MEDICATION_CHAT_SCHEMA_VERSION = "medication-chat-result-v1"


class AnswerMedicationQuestionUseCase:
    _EXACT_PRODUCT_REQUIRED_PATTERN = re.compile(
        r"복용법|사용법|어떻게\s*(?:먹|복용)|"
        r"몇\s*(?:정|캡슐|포)|용량|횟수|간격|"
        r"하루|1일|임신|수유|소아|어린이|"
        r"상호작용|같이\s*먹|함께\s*먹"
    )

    def __init__(
        self,
        *,
        context_provider: ActiveIntakeContextProvider,
        guide_repository: MedicationGuideRepository,
        interaction_rule_repository: InteractionRuleRepository,
        knowledge_retriever: MedicationKnowledgeRetriever,
        answer_generator: MedicationAnswerGenerator,
        grounded_claim_validator: GroundedClaimValidator,
    ) -> None:
        self._context_provider = context_provider
        self._guide_repository = guide_repository
        self._interaction_rule_repository = interaction_rule_repository
        self._knowledge_retriever = knowledge_retriever
        self._answer_generator = answer_generator
        self._grounded_claim_validator = grounded_claim_validator
        self._assembler = MedicationAnswerAssembler()

    async def execute(
        self,
        request: MedicationChatRequest,
        *,
        limit: int = 5,
    ) -> MedicationChatResult:
        context = await self._context_provider.get_active_context(
            user_id=request.user_id,
            care_episode_id=request.care_episode_id,
        )
        query_plan = MedicationKnowledgeQueryBuilder().build(
            request.question,
        )
        interaction_question = query_plan.interaction_pair is not None or self._is_interaction_question(
            request.question
        )
        rules = await self._interaction_rule_repository.find_approved_rules(
            context=context,
        )
        chunks, rag_unavailable = await self._retrieve_knowledge(
            request=request,
            context=context,
            rules=rules,
            limit=limit,
        )
        has_supplement_evidence = self._has_supplement_evidence(
            request.question,
            chunks=chunks,
        )
        guide_lookup = (
            MedicationGuideLookup()
            if (
                query_plan.interaction_pair is not None
                or (has_supplement_evidence and not query_plan.has_medication_product_cue)
            )
            else await self._find_guide(
                request=request,
                context=context,
                interaction_question=interaction_question,
            )
        )
        family_reference = False
        if (
            guide_lookup.is_ambiguous
            and guide_lookup.representative_guide is not None
            and not self._EXACT_PRODUCT_REQUIRED_PATTERN.search(
                request.question,
            )
        ):
            family_reference = True
            guide_lookup = guide_lookup.model_copy(
                update={
                    "guide": guide_lookup.representative_guide,
                    "is_ambiguous": False,
                }
            )
        if guide_lookup.is_ambiguous and not self._has_supplement_evidence(
            request.question,
            chunks=chunks,
        ):
            return self._clarification_result(
                request=request,
                context=context,
                guide_lookup=guide_lookup,
            )
        route = self._resolve_route(
            request=request,
            context=context,
            guide_lookup=guide_lookup,
            interaction_question=interaction_question,
            chunks=chunks,
        )
        safety_status = SafetyStatus.RESTRICTED if rag_unavailable else SafetyStatus.SAFE
        safety_reason_codes = ["RAG_UNAVAILABLE"] if rag_unavailable else []
        draft = MedicationChatResult(
            request_id=request.request_id,
            answer=self._assembler.assemble(
                context=context,
                guide=guide_lookup.guide,
                rules=rules,
                chunks=chunks,
                interaction_question=interaction_question,
                family_reference=family_reference,
            ),
            route=route,
            safety_status=safety_status,
            safety_reason_codes=safety_reason_codes,
            sources=self._build_sources(
                context=context,
                guide_lookup=guide_lookup,
                rules=rules,
                chunks=chunks,
            ),
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=self._context_hash(context),
        )
        generated = await self._answer_generator.generate(
            request=request,
            context=context,
            result=draft,
        )
        return await self._grounded_claim_validator.validate(
            context=context,
            result=generated,
        )

    async def _find_guide(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        interaction_question: bool,
    ) -> MedicationGuideLookup:
        if interaction_question:
            return MedicationGuideLookup()
        for candidate in self._product_name_candidates(
            request.question,
            context=context,
        ):
            lookup = await self._guide_repository.find_by_name(candidate)
            if lookup.guide is not None or lookup.is_ambiguous:
                return lookup
        return MedicationGuideLookup()

    async def _retrieve_knowledge(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        rules: list[InteractionRuleFact],
        limit: int,
    ) -> tuple[list, bool]:
        try:
            chunks = await self._knowledge_retriever.search(
                question=request.question,
                medication_names=[item.name for item in context.medications],
                supplement_names=[item.name for item in context.supplements],
                interaction_pair_keys=[rule.pair_key for rule in rules],
                limit=limit,
            )
        except Exception:
            return [], True
        return chunks, False

    @staticmethod
    def _resolve_route(
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
        interaction_question: bool,
        chunks: list,
    ) -> MedicationChatRoute:
        if interaction_question:
            return MedicationChatRoute.INTERACTION
        if request.care_episode_id is not None and context.medications:
            return MedicationChatRoute.ACTIVE_INTAKE
        if guide_lookup.guide is not None:
            return MedicationChatRoute.MEDICATION_GUIDE
        if AnswerMedicationQuestionUseCase._has_supplement_evidence(
            request.question,
            chunks=chunks,
        ):
            return MedicationChatRoute.SUPPLEMENT_GUIDE
        if AnswerMedicationQuestionUseCase._is_supplement_question(request.question):
            return MedicationChatRoute.SUPPLEMENT_GUIDE
        return MedicationChatRoute.GENERAL_GUIDANCE

    @staticmethod
    def _has_supplement_evidence(
        question: str,
        *,
        chunks: list,
    ) -> bool:
        supplement_types = {
            KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            KnowledgeDocumentType.SUPPLEMENT_CODE,
            KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH,
        }
        pair = find_supplement_interaction_pair(question)
        question_key = "".join(question.casefold().split())
        for chunk in chunks:
            metadata = chunk.metadata
            if (
                pair is not None
                and metadata.document_type == KnowledgeDocumentType.RESEARCH_ARTICLE
                and supplement_pair_matches_text(
                    pair,
                    metadata.title,
                    chunk.content,
                    *metadata.ingredient_names,
                )
            ):
                return True
            if metadata.document_type not in supplement_types:
                continue
            if not metadata.ingredient_names:
                return True
            if any("".join(name.casefold().split()) in question_key for name in metadata.ingredient_names):
                return True
        return False

    @staticmethod
    def _product_name_candidates(
        question: str,
        *,
        context: ActiveIntakeContext,
    ) -> list[str]:
        candidates = [
            medication.name for medication in context.medications if medication.name in question or "이 약" in question
        ]
        stopwords = {
            "어떤",
            "약인가요",
            "알려줘",
            "알려주세요",
            "주의사항",
            "복용법",
            "효능",
        }
        for token in re.findall(r"[가-힣A-Za-z0-9.+-]{2,}", question):
            normalized = re.sub(
                r"(은|는|이|가|을|를|과|와|의|도)$",
                "",
                token,
            )
            if normalized and normalized not in stopwords:
                candidates.append(normalized)
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _is_interaction_question(question: str) -> bool:
        return any(
            keyword in question
            for keyword in (
                "상호작용",
                "같이 먹",
                "함께 먹",
                "병용",
                "조합",
            )
        )

    @staticmethod
    def _is_supplement_question(question: str) -> bool:
        return bool(known_supplement_names_in(question)) or any(
            keyword in question
            for keyword in (
                "영양제",
                "비타민",
                "오메가",
                "마그네슘",
                "유산균",
                "프로바이오틱스",
            )
        )

    @staticmethod
    def _context_hash(context: ActiveIntakeContext) -> str:
        payload = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _clarification_result(
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
    ) -> MedicationChatResult:
        names = ", ".join(guide_lookup.candidate_names[:5])
        return MedicationChatResult(
            request_id=request.request_id,
            answer=(
                "같은 이름으로 여러 제품이 검색되었습니다. 약봉투의 정확한 "
                f"제품명을 확인해 주세요. 성분명도 함께 알려주면 더 정확히 "
                f"찾을 수 있습니다. 검색된 제품: {names}"
            ),
            route=MedicationChatRoute.CLARIFICATION,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=["AMBIGUOUS_MEDICATION_NAME"],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=AnswerMedicationQuestionUseCase._context_hash(context),
        )

    @staticmethod
    def _build_sources(
        *,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list,
    ) -> list[MedicationChatSource]:
        sources = [
            MedicationChatSource(
                kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                title=f"사용자 확정 복약정보 · {item.name}",
                medication_id=item.medication_id,
                care_episode_id=item.care_episode_id,
            )
            for item in context.medications
        ]
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.PATIENT_SUPPLEMENT,
                title=f"사용자 복용 영양제 · {item.name}",
                user_supplement_id=item.registration_id,
            )
            for item in context.supplements
        )
        if guide_lookup.guide is not None:
            sources.append(
                MedicationChatSource(
                    kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                    title=f"e약은요 · {guide_lookup.guide.product_name}",
                    organization="식품의약품안전처",
                    medication_guide_id=(guide_lookup.guide.medication_guide_id),
                )
            )
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.INTERACTION_RULE,
                title=(f"승인된 상호작용 규칙 · {rule.left_name} · {rule.right_name}"),
                url=rule.source_urls[0] if rule.source_urls else None,
                interaction_rule_id=rule.interaction_rule_id,
            )
            for rule in rules
        )
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                title=chunk.metadata.title,
                organization=chunk.metadata.provider,
                url=chunk.metadata.source_url,
                dataset_key="MEDICATION_KNOWLEDGE",
                dataset_version=chunk.metadata.dataset_version,
                vector_chunk_id=chunk.point_id,
                source_page_number=chunk.metadata.page_start,
                similarity_score=chunk.similarity_score,
            )
            for chunk in chunks
        )
        return sources
