import pytest

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.schemas.intake_report import IntakeReportResult
from ai_worker.services.intake_report_core_service import (
    IntakeReportCoreService,
    build_intake_report_core_service,
)


class FakeUseCase:
    def __init__(self) -> None:
        self.user_id: int | None = None

    async def execute(self, *, user_id: int) -> IntakeReportResult:
        self.user_id = user_id
        return IntakeReportResult.empty(user_id=user_id)


async def test_core_service_reuses_report_use_case_entrypoint() -> None:
    use_case = FakeUseCase()
    service = IntakeReportCoreService(use_case=use_case)

    result = await service.generate(user_id=1)

    assert result.status == IntakeReportResult.empty(user_id=1).status
    assert use_case.user_id == 1


def test_builder_rejects_missing_openai_key() -> None:
    settings = Config(OPENAI_API_KEY=None, _env_file=None)

    with pytest.raises(AIConfigurationError):
        build_intake_report_core_service(
            settings=settings,
            qdrant_client=object(),
        )
