from dataclasses import dataclass

from ai_worker.schemas.knowledge import (
    KnowledgeContentKind,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan


@dataclass(frozen=True)
class ParentContextResolution:
    chunks: list[RetrievedKnowledgeChunk]
    child_count: int
    attached_parent_count: int
    rejected_parent_mismatch_count: int


class ParentContextResolver:
    """검색된 작은 청크에 같은 절의 인접 문맥만 보수적으로 결합한다."""

    _MAX_CONTEXT_CHUNKS = 3

    def resolve(
        self,
        *,
        children: list[RetrievedKnowledgeChunk],
        candidates: list[RetrievedKnowledgeChunk],
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> ParentContextResolution:
        unique_candidates = self._unique_by_chunk_id(candidates)
        resolved: list[RetrievedKnowledgeChunk] = []
        expanded_parent_keys: set[tuple] = set()
        attached_parent_count = 0
        rejected_parent_mismatch_count = 0

        for child in children:
            parent_key = self._parent_key(child)
            if parent_key in expanded_parent_keys:
                continue
            compatible, rejected = self._compatible_contexts(
                child=child,
                candidates=unique_candidates,
                query_plan=query_plan,
            )
            rejected_parent_mismatch_count += rejected
            if compatible:
                resolved.append(self._merge_context(child, compatible))
                expanded_parent_keys.add(parent_key)
                attached_parent_count += 1
            else:
                resolved.append(child)

        return ParentContextResolution(
            chunks=resolved,
            child_count=len(children),
            attached_parent_count=attached_parent_count,
            rejected_parent_mismatch_count=rejected_parent_mismatch_count,
        )

    def _compatible_contexts(
        self,
        *,
        child: RetrievedKnowledgeChunk,
        candidates: list[RetrievedKnowledgeChunk],
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> tuple[list[RetrievedKnowledgeChunk], int]:
        compatible: list[RetrievedKnowledgeChunk] = []
        rejected = 0
        for candidate in candidates:
            if candidate.chunk_id == child.chunk_id:
                continue
            if abs(candidate.metadata.chunk_index - child.metadata.chunk_index) != 1:
                continue
            if self._is_compatible_parent_context(
                child=child,
                candidate=candidate,
                query_plan=query_plan,
            ):
                compatible.append(candidate)
            else:
                rejected += 1
        compatible.sort(key=lambda item: item.metadata.chunk_index)
        return compatible[: self._MAX_CONTEXT_CHUNKS - 1], rejected

    @classmethod
    def _is_compatible_parent_context(
        cls,
        *,
        child: RetrievedKnowledgeChunk,
        candidate: RetrievedKnowledgeChunk,
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        child_metadata = child.metadata
        candidate_metadata = candidate.metadata
        if child_metadata.content_kind != KnowledgeContentKind.TEXT:
            return False
        if candidate_metadata.content_kind != KnowledgeContentKind.TEXT:
            return False
        if cls._parent_key(child) != cls._parent_key(candidate):
            return False
        child_entities = cls._metadata_entities(child)
        candidate_entities = cls._metadata_entities(candidate)
        if child_entities != candidate_entities:
            return False
        query_entities = cls._normalized_names(query_plan.entity_names)
        return not query_entities or bool(query_entities.intersection(child_entities))

    @staticmethod
    def _merge_context(
        child: RetrievedKnowledgeChunk,
        contexts: list[RetrievedKnowledgeChunk],
    ) -> RetrievedKnowledgeChunk:
        """선택된 child의 식별자는 유지하고, 검증된 인접 본문만 덧붙인다."""
        ordered = sorted(
            [child, *contexts],
            key=lambda chunk: chunk.metadata.chunk_index,
        )
        content = "\n\n".join(chunk.content.strip() for chunk in ordered)
        embedding_text = "\n\n".join(chunk.embedding_text.strip() for chunk in ordered)
        return child.model_copy(
            update={
                "content": content,
                "embedding_text": embedding_text,
                "token_count": sum(chunk.token_count for chunk in ordered),
            }
        )

    @staticmethod
    def _parent_key(chunk: RetrievedKnowledgeChunk) -> tuple:
        metadata = chunk.metadata
        return (
            metadata.source_id,
            metadata.document_id,
            metadata.document_type,
            metadata.section_type,
            metadata.section_title,
            metadata.table_group_id,
        )

    @classmethod
    def _metadata_entities(cls, chunk: RetrievedKnowledgeChunk) -> set[str]:
        metadata = chunk.metadata
        return cls._normalized_names(
            [
                *metadata.drug_names,
                *metadata.ingredient_names,
                *metadata.food_names,
            ]
        )

    @staticmethod
    def _normalized_names(values: list[str]) -> set[str]:
        return {"".join(value.casefold().split()) for value in values if value.strip()}

    @staticmethod
    def _unique_by_chunk_id(
        candidates: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        seen: set[str] = set()
        unique: list[RetrievedKnowledgeChunk] = []
        for candidate in candidates:
            if candidate.chunk_id in seen:
                continue
            seen.add(candidate.chunk_id)
            unique.append(candidate)
        return unique
