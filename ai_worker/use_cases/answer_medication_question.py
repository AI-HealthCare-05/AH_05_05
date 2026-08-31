import hashlib
import json
import re

from ai_worker.domain.chat_content_compactor import (
    ANSWER_COMPACTION_MARKER,
    compact_chat_content,
)
from ai_worker.domain.interaction_question_detector import (
    is_interaction_question,
)
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
from ai_worker.observability.chat_tracer import ChatTracer, NoOpChatTracer
from ai_worker.rag.metadata.supplement_interaction_registry import (
    find_supplement_interaction_pair,
    known_supplement_names_in,
    supplement_pair_matches_text,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
    MedicationKnowledgeQueryPlan,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSectionType,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationChatProgress,
    MedicationChatProgressCallback,
    MedicationChatProgressStage,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
    MedicationGuideLookup,
)

MEDICATION_CHAT_PROMPT_VERSION = "medication-chat-prompt-v3"
MEDICATION_CHAT_SCHEMA_VERSION = "medication-chat-result-v1"


class AnswerMedicationQuestionUseCase:
    _MAX_PRODUCT_NAME_CANDIDATES = 12
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
        tracer: ChatTracer | None = None,
    ) -> None:
        self._context_provider = context_provider
        self._guide_repository = guide_repository
        self._interaction_rule_repository = interaction_rule_repository
        self._knowledge_retriever = knowledge_retriever
        self._answer_generator = answer_generator
        self._grounded_claim_validator = grounded_claim_validator
        self._tracer = tracer or NoOpChatTracer()
        self._assembler = MedicationAnswerAssembler()

    async def execute(
        self,
        request: MedicationChatRequest,
        *,
        limit: int = 5,
        progress_callback: MedicationChatProgressCallback | None = None,
    ) -> MedicationChatResult:
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.QUESTION_CHECKING,
        )
        async with self._tracer.span(
            "patient_context.load",
            run_type="tool",
        ) as context_span:
            context = await self._context_provider.get_active_context(
                user_id=request.user_id,
                care_episode_id=request.care_episode_id,
            )
            context_span.end(
                {
                    "medication_count": len(context.medications),
                    "supplement_count": len(context.supplements),
                    "context_hash": self._context_hash(context),
                }
            )
        async with self._tracer.span("query.plan") as query_span:
            query_plan = MedicationKnowledgeQueryBuilder().build(
                request.question,
            )
            query_outputs = {
                "entity_count": len(query_plan.entity_names),
                "section_count": len(query_plan.section_types),
                "interaction_pair_present": (query_plan.interaction_pair is not None),
                "medication_product_cue": (query_plan.has_medication_product_cue),
            }
            if self._tracer.capture_content:
                query_outputs["entity_names"] = query_plan.entity_names
                query_outputs["entity_roles"] = [entity.entity_type.value for entity in query_plan.entities]
                query_outputs["entity_role_candidates"] = [
                    [candidate.value for candidate in entity.candidate_types] for entity in query_plan.entities
                ]
            query_outputs["interaction_pair_count"] = len(
                query_plan.interaction_pairs,
            )
            query_span.end(query_outputs)
        interaction_question = query_plan.interaction_pair is not None or self._is_interaction_question(
            request.question
        )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.EVIDENCE_SEARCHING,
        )
        async with self._tracer.span(
            "interaction_rules.search",
            run_type="tool",
        ) as rules_span:
            rules = await self._interaction_rule_repository.find_approved_rules(
                context=context,
            )
            rules_span.end({"approved_rule_count": len(rules)})
        async with self._tracer.span(
            "rag.retrieve",
            run_type="retriever",
        ) as rag_span:
            retrieval, rag_unavailable = await self._retrieve_knowledge(
                request=request,
                context=context,
                rules=rules,
                limit=limit,
            )
            chunks = retrieval.chunks
            rag_span.end(
                {
                    **retrieval.diagnostics.model_dump(),
                    "rag_unavailable": rag_unavailable,
                    "document_types": sorted({chunk.metadata.document_type.value for chunk in chunks}),
                    "drug_encyclopedia_evidence_count": sum(
                        chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA for chunk in chunks
                    ),
                }
            )
        has_supplement_evidence = self._has_supplement_evidence(
            request.question,
            chunks=chunks,
        )
        async with self._tracer.span(
            "medication_guide.lookup",
            run_type="tool",
        ) as guide_span:
            guide_lookup = (
                MedicationGuideLookup()
                if (
                    query_plan.interaction_pair is not None
                    or (has_supplement_evidence and not query_plan.has_medication_product_cue)
                )
                else await self._find_guide(
                    request=request,
                    context=context,
                    query_plan=query_plan,
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
            guide_span.end(
                {
                    "guide_found": guide_lookup.guide is not None,
                    "ambiguous": guide_lookup.is_ambiguous,
                    "candidate_count": len(guide_lookup.candidate_names),
                    "family_reference": family_reference,
                }
            )
        has_drug_encyclopedia_evidence = self._has_drug_encyclopedia_evidence(chunks)
        can_use_ingredient_family_fallback = (
            has_drug_encyclopedia_evidence and not query_plan.has_medication_product_cue
        )
        if (
            guide_lookup.is_ambiguous
            and not self._has_supplement_evidence(
                request.question,
                chunks=chunks,
            )
            and not can_use_ingredient_family_fallback
        ):
            await self._report_progress(
                progress_callback,
                MedicationChatProgressStage.SAFETY_CHECKING,
            )
            return self._clarification_result(
                request=request,
                context=context,
                guide_lookup=guide_lookup,
            )
        answer_chunks = self._authoritative_chunks(
            guide_lookup=guide_lookup,
            chunks=chunks,
            prefer_supplement=(
                has_supplement_evidence and not query_plan.has_medication_product_cue and not interaction_question
            ),
        )
        ingredient_family_reference = guide_lookup.guide is None and self._has_drug_encyclopedia_evidence(answer_chunks)
        unsupported_pairs = self._unsupported_interaction_pairs(
            query_plan=query_plan,
            rules=rules,
            chunks=answer_chunks,
        )
        route = self._resolve_route(
            request=request,
            context=context,
            guide_lookup=guide_lookup,
            interaction_question=interaction_question,
            chunks=answer_chunks,
        )
        safety_status = SafetyStatus.RESTRICTED if rag_unavailable else SafetyStatus.SAFE
        safety_reason_codes = ["RAG_UNAVAILABLE"] if rag_unavailable else []
        async with self._tracer.span("answer.draft") as draft_span:
            draft = MedicationChatResult(
                request_id=request.request_id,
                answer=self._assembler.assemble(
                    context=context,
                    guide=guide_lookup.guide,
                    rules=rules,
                    chunks=answer_chunks,
                    interaction_question=interaction_question,
                    family_reference=family_reference,
                    ingredient_family_reference=(ingredient_family_reference),
                    unsupported_pairs=unsupported_pairs,
                ),
                route=route,
                safety_status=safety_status,
                safety_reason_codes=safety_reason_codes,
                sources=self._build_sources(
                    context=context,
                    guide_lookup=guide_lookup,
                    rules=rules,
                    chunks=answer_chunks,
                ),
                prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
                schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
                context_hash=self._context_hash(context),
            )
            draft_span.end(
                {
                    "route": draft.route.value,
                    "source_count": len(draft.sources),
                    "safety_status": draft.safety_status.value,
                }
            )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.ANSWER_GENERATING,
        )
        async with self._tracer.span("llm.generate", run_type="llm") as llm_span:
            generated = await self._answer_generator.generate(
                request=request,
                context=context,
                result=draft,
            )
            generated = generated.model_copy(
                update={
                    "answer": compact_chat_content(
                        generated.answer,
                        marker=ANSWER_COMPACTION_MARKER,
                    )
                }
            )
            llm_span.end(
                {
                    "route": generated.route.value,
                    "source_count": len(generated.sources),
                }
            )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.SAFETY_CHECKING,
        )
        async with self._tracer.span("safety.validate") as safety_span:
            validated = await self._grounded_claim_validator.validate(
                context=context,
                result=generated,
            )
            safety_span.end(
                {
                    "status": validated.safety_status.value,
                    "reason_codes": validated.safety_reason_codes,
                }
            )
        return validated

    @staticmethod
    async def _report_progress(
        callback: MedicationChatProgressCallback | None,
        stage: MedicationChatProgressStage,
    ) -> None:
        if callback is None:
            return
        await callback(MedicationChatProgress.for_stage(stage))

    async def _find_guide(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        query_plan: MedicationKnowledgeQueryPlan,
        interaction_question: bool,
    ) -> MedicationGuideLookup:
        if interaction_question:
            return MedicationGuideLookup()
        for candidate in self._product_name_candidates(
            request.question,
            context=context,
            query_plan=query_plan,
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
    ) -> tuple[KnowledgeRetrievalResult, bool]:
        try:
            retrieval = await self._knowledge_retriever.search_with_diagnostics(
                question=request.question,
                medication_names=[item.name for item in context.medications],
                supplement_names=[item.name for item in context.supplements],
                interaction_pair_keys=[rule.pair_key for rule in rules],
                limit=limit,
            )
        except Exception:
            return self._empty_retrieval_result(), True
        return retrieval, False

    @staticmethod
    def _empty_retrieval_result() -> KnowledgeRetrievalResult:
        return KnowledgeRetrievalResult(
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=0,
                entity_filtered_count=0,
                broad_candidate_count=0,
                fallback_used=False,
                eligible_candidate_count=0,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=0,
                max_raw_score=None,
                max_score=None,
            )
        )

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
        if AnswerMedicationQuestionUseCase._has_drug_encyclopedia_evidence(
            chunks,
        ):
            return MedicationChatRoute.MEDICATION_GUIDE
        if AnswerMedicationQuestionUseCase._is_supplement_question(request.question):
            return MedicationChatRoute.SUPPLEMENT_GUIDE
        return MedicationChatRoute.GENERAL_GUIDANCE

    @staticmethod
    def _has_drug_encyclopedia_evidence(chunks: list) -> bool:
        return any(chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA for chunk in chunks)

    @staticmethod
    def _authoritative_chunks(
        *,
        guide_lookup: MedicationGuideLookup,
        chunks: list,
        prefer_supplement: bool = False,
    ) -> list:
        if prefer_supplement:
            return [
                chunk for chunk in chunks if chunk.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA
            ]
        if guide_lookup.guide is None:
            return chunks
        product_claim_sections = {
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.DAILY_INTAKE,
            KnowledgeSectionType.CAUTION,
            KnowledgeSectionType.ADVERSE_EVENT,
        }
        return [
            chunk
            for chunk in chunks
            if not (
                chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA
                and chunk.metadata.section_type in product_claim_sections
            )
        ]

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
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[str]:
        candidates = [medication.name for medication in context.medications if medication.name in question]
        if "이 약" in question and len(context.medications) == 1:
            candidates.append(context.medications[0].name)
        candidates.extend(
            entity.canonical_name for entity in query_plan.entities if entity.kind == InteractionEntityKind.DRUG
        )
        return list(dict.fromkeys(candidates))[: AnswerMedicationQuestionUseCase._MAX_PRODUCT_NAME_CANDIDATES]

    @staticmethod
    def _is_interaction_question(question: str) -> bool:
        return is_interaction_question(question)

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

    @classmethod
    def _unsupported_interaction_pairs(
        cls,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        chunks: list,
    ) -> list[str]:
        if len(query_plan.interaction_pairs) <= 1:
            return []

        evidence_texts = [
            " ".join(
                [
                    chunk.metadata.title,
                    chunk.content,
                    *chunk.metadata.drug_names,
                    *chunk.metadata.ingredient_names,
                ]
            )
            for chunk in chunks
        ]
        rule_pairs = [
            {
                cls._normalize_entity_name(rule.left_name),
                cls._normalize_entity_name(rule.right_name),
            }
            for rule in rules
        ]
        unsupported: list[str] = []
        for pair in query_plan.interaction_pairs:
            pair_names = {
                cls._normalize_entity_name(pair.left_name),
                cls._normalize_entity_name(pair.right_name),
            }
            has_rule = pair_names in rule_pairs
            has_chunk = any(
                all(name in cls._normalize_entity_name(text) for name in pair_names) for text in evidence_texts
            )
            if not has_rule and not has_chunk:
                unsupported.append(
                    f"{pair.left_name} ↔ {pair.right_name}",
                )
        return unsupported

    @staticmethod
    def _normalize_entity_name(value: str) -> str:
        return "".join(value.casefold().split())

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
