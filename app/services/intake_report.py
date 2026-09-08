import asyncio
import time
from collections.abc import Callable

from ai_worker.domain.errors import AIWorkerError
from ai_worker.observability.chat_tracer import (
    ChatTracer,
    NoOpChatTracer,
)
from ai_worker.schemas.intake_report import IntakeReportResult
from ai_worker.services.intake_report_core_service import IntakeReportCoreService
from app.core.exceptions import (
    IntakeReportProcessingFailedError,
    IntakeReportTimeoutError,
    IntakeReportUpstreamUnavailableError,
)
from app.models.users import User

INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS = 30.0


class IntakeReportApplicationService:
    """HTTP 요청 경계에서 보고서 Core 호출·시간 제한·관측성을 담당한다."""

    def __init__(
        self,
        *,
        core_service: IntakeReportCoreService,
        tracer: ChatTracer | None = None,
        clock: Callable[[], float] = time.perf_counter,
        timeout_seconds: float = INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS,
    ) -> None:
        self._core_service = core_service
        self._tracer = tracer or NoOpChatTracer()
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    async def generate(self, *, user: User) -> IntakeReportResult:
        metadata = {
            "user_key": self._tracer.anonymize_identifier(user.id),
        }
        started_at = self._clock()
        async with self._tracer.span(
            "intake-report.generate",
            root=True,
            inputs={},
            metadata=metadata,
        ) as root_span:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    result = await self._core_service.generate(user_id=user.id)
            except TimeoutError as error:
                root_span.end(
                    {
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                        "duration_ms": self._duration_ms(started_at),
                    }
                )
                raise IntakeReportTimeoutError from error
            except AIWorkerError as error:
                root_span.end(
                    {
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                        "duration_ms": self._duration_ms(started_at),
                    }
                )
                raise IntakeReportUpstreamUnavailableError from error
            except asyncio.CancelledError:
                root_span.end(
                    {
                        "status": "CANCELLED",
                        "duration_ms": self._duration_ms(started_at),
                    }
                )
                raise
            except Exception as error:
                root_span.end(
                    {
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                        "duration_ms": self._duration_ms(started_at),
                    }
                )
                raise IntakeReportProcessingFailedError from error

            root_span.end(
                {
                    "status": "COMPLETED",
                    "report_status": result.status.value,
                    "active_medication_count": (result.data_availability.active_medication_count),
                    "active_supplement_count": (result.data_availability.active_supplement_count),
                    "review_card_count": len(result.review_cards),
                    "source_count": self._source_count(result),
                    "duration_ms": self._duration_ms(started_at),
                }
            )
            return result

    @staticmethod
    def _source_count(result: IntakeReportResult) -> int:
        return sum(len(card.sources) for card in result.review_cards) + sum(
            len(guide.sources) for guide in result.product_guides
        )

    def _duration_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1000))
