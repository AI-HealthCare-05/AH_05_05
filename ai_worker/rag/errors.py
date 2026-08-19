from enum import StrEnum


class RetrievalFailureStage(StrEnum):
    EMBEDDING = "EMBEDDING"
    VECTOR_STORE = "VECTOR_STORE"


class GuidelineRetrievalError(RuntimeError):
    def __init__(
        self,
        *,
        stage: RetrievalFailureStage,
        message: str,
    ) -> None:
        super().__init__(message)
        self.stage = stage
