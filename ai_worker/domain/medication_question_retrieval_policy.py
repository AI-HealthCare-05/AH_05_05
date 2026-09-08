from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationQuestionResolution,
    MedicationQuestionScope,
)


def should_execute_source_backed_retrieval(
    resolution: MedicationQuestionResolution | None,
) -> bool:
    """확인된 대상이 없는 질문을 임의 RAG 검색으로 확장하지 않는다."""

    if resolution is None:
        # 하위 호환 경로에서는 resolver가 없으므로 기존 검색 동작을 유지한다.
        return True
    if resolution.scope != MedicationQuestionScope.IN_SCOPE:
        return False
    if resolution.status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED:
        return False
    return not (resolution.entity_resolution_available and not resolution.entities)
