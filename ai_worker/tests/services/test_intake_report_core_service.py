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


def test_stale_temporary_flag_cannot_bypass_real_ai_configuration() -> None:
    settings = Config(OPENAI_API_KEY=None, INTAKE_REPORT_REVIEWED_V11_ENABLED=True, _env_file=None)
    with pytest.raises(AIConfigurationError):
        build_intake_report_core_service(settings=settings, qdrant_client=object())


@pytest.mark.parametrize("rag_enabled", [True, False])
def test_builder_uses_structured_evidence_card_generator(monkeypatch, rag_enabled) -> None:
    import ai_worker.services.intake_report_core_service as module

    constructor = module.OpenAIIntakeReportCardsGenerator
    options = {}

    def capture_options(**kwargs):
        options.update(kwargs)
        return constructor(**kwargs)

    monkeypatch.setattr(module, "OpenAIIntakeReportCardsGenerator", capture_options)
    settings = Config(
        OPENAI_API_KEY="offline-not-a-real-key",
        KNOWLEDGE_SEARCH_MODE="DENSE",
        INTAKE_REPORT_RAG_ENABLED=rag_enabled,
        _env_file=None,
    )
    service = build_intake_report_core_service(settings=settings, qdrant_client=object(), tracer=None)
    # The production entrypoint must not silently keep the legacy Markdown
    # generator even when the DTO and frontend accept v11 cards.
    generator = service._use_case._generator
    if rag_enabled:
        assert type(generator).__name__ == "RagIntakeReportCardsGenerator"
        generator = generator._base_generator
    assert type(generator).__name__ == "OpenAIIntakeReportCardsGenerator"
    assert options["include_fixed_lifestyle_guidance"] is (not rag_enabled)
    assert options["timeout_seconds"] >= 75.0
    assert options["enable_plain_language"] is False
    assert generator._plain_language_refiner is None
    assert generator._generation_timeout_seconds == 90.0


def test_builder_wires_bounded_candidate_selector_using_configured_model() -> None:
    from ai_worker.llm.generators.medication_candidate_selector import OpenAIMedicationCandidateSelector

    settings = Config(OPENAI_API_KEY="offline-not-a-real-key", KNOWLEDGE_SEARCH_MODE="DENSE", _env_file=None)
    service = build_intake_report_core_service(settings=settings, qdrant_client=object())

    selector = service._use_case._guide_repository._candidate_selector
    assert isinstance(selector, OpenAIMedicationCandidateSelector)
    assert selector.model_name == settings.OPENAI_CHAT_MODEL
    assert selector._timeout_seconds <= 5.0


def test_builder_uses_all_episode_medications_for_reports(monkeypatch) -> None:
    import ai_worker.services.intake_report_core_service as module

    captured = {}
    provider_type = module.DbActiveIntakeContextProvider

    def capture_provider(**kwargs):
        captured.update(kwargs)
        return provider_type(**kwargs)

    monkeypatch.setattr(module, "DbActiveIntakeContextProvider", capture_provider)
    settings = Config(OPENAI_API_KEY="offline-not-a-real-key", KNOWLEDGE_SEARCH_MODE="DENSE", _env_file=None)

    build_intake_report_core_service(settings=settings, qdrant_client=object())

    assert captured["include_all_episode_medications"] is True
