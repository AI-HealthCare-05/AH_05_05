class AIWorkerError(RuntimeError):
    """FastAPI가 안정적으로 변환할 수 있는 AI Worker 예외 계약."""

    code = "AI_WORKER_ERROR"
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AIConfigurationError(AIWorkerError):
    code = "AI_CONFIGURATION_ERROR"


class PatientContextNotFoundError(AIWorkerError):
    code = "PATIENT_CONTEXT_NOT_FOUND"


class UnconfirmedPatientContextError(AIWorkerError):
    code = "PATIENT_CONTEXT_UNCONFIRMED"


class ChatClassificationError(AIWorkerError):
    code = "CHAT_CLASSIFICATION_FAILED"
    retryable = True


class ChatAnswerGenerationError(AIWorkerError):
    code = "CHAT_ANSWER_GENERATION_FAILED"
    retryable = True

    def __init__(self, message: str, *, reason_code: str = "CLIENT_ERROR") -> None:
        super().__init__(message)
        self.reason_code = reason_code
