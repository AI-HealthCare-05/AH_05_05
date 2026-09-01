import hashlib
import json
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.evaluators.knowledge_evaluation_metrics import (
    calculate_knowledge_evaluation_metrics,
)
from ai_worker.schemas.knowledge import (
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationCase,
    KnowledgeEvaluationManifest,
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
)


class KnowledgeSearchStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]: ...


class KnowledgeRetrievalEvaluator:
    _EVALUATOR_VERSION = "knowledge-retrieval-evaluator-v2"

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: KnowledgeSearchStore,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._timer = timer

    async def evaluate(
        self,
        manifest: KnowledgeEvaluationManifest,
    ) -> KnowledgeEvaluationReport:
        query_results: list[KnowledgeQueryEvaluationResult] = []

        for case in manifest.cases:
            query_vector = await self._embedding_provider.embed_query(case.query)
            started_at = self._timer()
            retrieved = await self._vector_store.search(
                query_vector=query_vector,
                search_query=self._build_search_query(
                    case=case,
                    dataset_version=manifest.dataset_version,
                ),
            )
            latency_ms = (self._timer() - started_at) * 1000.0
            query_results.append(
                self._evaluate_query(
                    case=case,
                    retrieved=retrieved,
                    latency_ms=latency_ms,
                )
            )

        metrics = calculate_knowledge_evaluation_metrics(query_results)
        thresholds = manifest.thresholds
        accuracy_passed = (
            metrics.hit_at_5 >= thresholds.min_hit_at_5
            and metrics.citation_accuracy >= thresholds.min_citation_accuracy
            and metrics.wrong_entity_mixing_count <= thresholds.max_wrong_entity_mixing_count
        )
        latency_passed = metrics.search_p95_ms <= thresholds.max_search_p95_ms

        return KnowledgeEvaluationReport(
            dataset_version=manifest.dataset_version,
            collection_name=self._vector_store.collection_name,
            query_count=len(query_results),
            hit_at_5=metrics.hit_at_5,
            mrr=metrics.mrr,
            citation_accuracy=metrics.citation_accuracy,
            duplicate_retrieval_rate=metrics.duplicate_retrieval_rate,
            wrong_entity_mixing_count=metrics.wrong_entity_mixing_count,
            search_p95_ms=metrics.search_p95_ms,
            evaluation_contract_hash=self._evaluation_contract_hash(
                manifest,
                embedding_model_name=self._embedding_provider.model_name,
                embedding_dimension=self._embedding_provider.dimension,
            ),
            accuracy_passed=accuracy_passed,
            latency_passed=latency_passed,
            passed=accuracy_passed and latency_passed,
            query_results=query_results,
        )

    @staticmethod
    def _evaluation_contract_hash(
        manifest: KnowledgeEvaluationManifest,
        *,
        embedding_model_name: str,
        embedding_dimension: int,
    ) -> str:
        contract = manifest.model_dump(
            mode="json",
            exclude={"dataset_version"},
        )
        contract["cases"] = sorted(
            contract["cases"],
            key=lambda case: case["query_id"],
        )
        contract["evaluator_version"] = KnowledgeRetrievalEvaluator._EVALUATOR_VERSION
        contract["embedding_model_name"] = embedding_model_name
        contract["embedding_dimension"] = embedding_dimension
        canonical = json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_search_query(
        *,
        case: KnowledgeEvaluationCase,
        dataset_version: str,
    ) -> KnowledgeSearchQuery:
        uses_exact_pair_filter = bool(case.interaction_pair_keys)
        return KnowledgeSearchQuery(
            query=case.query,
            dataset_version=dataset_version,
            document_types=case.document_types,
            drug_names=[] if uses_exact_pair_filter else case.drug_names,
            ingredient_names=[] if uses_exact_pair_filter else case.ingredient_names,
            interaction_type=case.interaction_type,
            interaction_pair_keys=case.interaction_pair_keys,
            special_populations=case.special_populations,
            section_types=case.section_types,
            limit=case.top_k,
        )

    @staticmethod
    def _evaluate_query(
        *,
        case: KnowledgeEvaluationCase,
        retrieved: list[RetrievedKnowledgeChunk],
        latency_ms: float,
    ) -> KnowledgeQueryEvaluationResult:
        relevant_positions = [
            index
            for index, result in enumerate(retrieved, start=1)
            if KnowledgeRetrievalEvaluator._is_relevant(case, result)
        ]
        first_relevant_rank = relevant_positions[0] if relevant_positions else None
        seen_hashes: set[str] = set()
        duplicate_count = 0
        for result in retrieved:
            content_hash = result.metadata.content_hash
            if content_hash in seen_hashes:
                duplicate_count += 1
            else:
                seen_hashes.add(content_hash)

        wrong_entity_mixing_count = sum(
            KnowledgeRetrievalEvaluator._is_disjoint_entity_result(
                case,
                result,
            )
            for result in retrieved
        )

        return KnowledgeQueryEvaluationResult(
            query_id=case.query_id,
            retrieved_document_ids=[result.metadata.document_id for result in retrieved],
            hit_at_5=(
                any(position <= 5 for position in relevant_positions)
                and KnowledgeRetrievalEvaluator._has_expected_section_coverage(
                    case,
                    retrieved[:5],
                )
            ),
            reciprocal_rank=(1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0),
            relevant_count=len(relevant_positions),
            retrieved_count=len(retrieved),
            duplicate_count=duplicate_count,
            wrong_entity_mixing_count=wrong_entity_mixing_count,
            search_latency_ms=round(max(latency_ms, 0.0), 3),
        )

    @staticmethod
    def _is_relevant(
        case: KnowledgeEvaluationCase,
        result: RetrievedKnowledgeChunk,
    ) -> bool:
        if result.metadata.document_id not in set(case.expected_document_ids):
            return False
        if case.expected_section_types and result.metadata.section_type not in set(case.expected_section_types):
            return False
        if case.expected_drug_names and set(result.metadata.drug_names).isdisjoint(case.expected_drug_names):
            return False
        if case.expected_ingredient_names and set(result.metadata.ingredient_names).isdisjoint(
            case.expected_ingredient_names
        ):
            return False
        if case.expected_interaction_pair_keys and set(result.metadata.interaction_pair_keys).isdisjoint(
            case.expected_interaction_pair_keys
        ):
            return False
        return True

    @staticmethod
    def _has_expected_section_coverage(
        case: KnowledgeEvaluationCase,
        retrieved: list[RetrievedKnowledgeChunk],
    ) -> bool:
        expected_sections = set(case.expected_section_types)
        if not expected_sections:
            return True

        covered_sections = {
            result.metadata.section_type
            for result in retrieved
            if result.metadata.document_id in set(case.expected_document_ids)
            and (
                not case.expected_drug_names or not set(result.metadata.drug_names).isdisjoint(case.expected_drug_names)
            )
            and (
                not case.expected_ingredient_names
                or not set(result.metadata.ingredient_names).isdisjoint(case.expected_ingredient_names)
            )
            and (
                not case.expected_interaction_pair_keys
                or not set(result.metadata.interaction_pair_keys).isdisjoint(case.expected_interaction_pair_keys)
            )
        }
        return expected_sections.issubset(covered_sections)

    @staticmethod
    def _is_disjoint_entity_result(
        case: KnowledgeEvaluationCase,
        result: RetrievedKnowledgeChunk,
    ) -> bool:
        if result.metadata.document_id in set(case.forbidden_document_ids):
            return True

        actual_drugs = set(result.metadata.drug_names)
        actual_ingredients = set(result.metadata.ingredient_names)
        if actual_drugs.intersection(case.forbidden_drug_names):
            return True
        if actual_ingredients.intersection(case.forbidden_ingredient_names):
            return True

        expected = set(case.expected_drug_names) | set(case.expected_ingredient_names)
        if not expected:
            return False
        actual = actual_drugs | actual_ingredients
        return bool(actual) and actual.isdisjoint(expected)
