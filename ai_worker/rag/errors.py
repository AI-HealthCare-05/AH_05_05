from enum import StrEnum

from ai_worker.domain.errors import AIWorkerError


class RetrievalFailureStage(StrEnum):
    EMBEDDING = "EMBEDDING"
    VECTOR_STORE = "VECTOR_STORE"


class GuidelineRetrievalError(AIWorkerError):
    code = "GUIDELINE_RETRIEVAL_FAILED"
    retryable = True

    def __init__(
        self,
        *,
        stage: RetrievalFailureStage,
        message: str,
    ) -> None:
        super().__init__(message)
        self.stage = stage


class KnowledgeDatasetVersionMismatchError(AIWorkerError):
    """비어 있지 않은 release에 요청 dataset이 없을 때의 구성 오류."""

    code = "KNOWLEDGE_DATASET_VERSION_MISMATCH"
