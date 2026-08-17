from ai_worker.domain.interfaces import (
    GuideGenerator,
    GuidelineConflictResolver,
    GuidelineRetriever,
    OutputSafetyValidator,
    PatientContextProvider,
)
from ai_worker.rag.query_builders.patient_query_builder import (
    PatientQueryBuilder,
)
from ai_worker.schemas.enums import (
    ConflictStatus,
    SafetyStatus,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
    RecoveryGuideResult,
)


class GenerateRecoveryGuideUseCase:
    def __init__(
        self,
        patient_context_provider: (
            PatientContextProvider
        ),
        query_builder: PatientQueryBuilder,
        retriever: GuidelineRetriever,
        conflict_resolver: (
            GuidelineConflictResolver
        ),
        guide_generator: GuideGenerator,
        safety_validator: OutputSafetyValidator,
    ) -> None:
        self._patient_context_provider = (
            patient_context_provider
        )
        self._query_builder = query_builder
        self._retriever = retriever
        self._conflict_resolver = (
            conflict_resolver
        )
        self._guide_generator = guide_generator
        self._safety_validator = safety_validator

    async def execute(
        self,
        user_id: int,
        care_episode_id: int,
        condition: str,
        topic: str,
        care_phase: str = "POST_DISCHARGE",
        limit: int = 5,
    ) -> RecoveryGuideResult:
        patient_context = (
            await self._patient_context_provider
            .get_patient_context(
                user_id=user_id,
                care_episode_id=care_episode_id,
            )
        )

        search_query = self._query_builder.build(
            patient_context=patient_context,
            condition=condition,
            topic=topic,
            care_phase=care_phase,
            limit=limit,
        )

        retrieved_chunks = (
            await self._retriever.search(
                search_query
            )
        )

        conflict_result = (
            await self._conflict_resolver.resolve(
                patient_context=patient_context,
                guideline_chunks=retrieved_chunks,
            )
        )

        guide_result = (
            await self._guide_generator.generate(
                patient_context=patient_context,
                guideline_chunks=(
                    conflict_result
                    .usable_guideline_chunks
                ),
            )
        )

        safety_result = (
            await self._safety_validator.validate(
                patient_context=patient_context,
                result=guide_result,
            )
        )

        final_status = safety_result.status
        reason_codes = list(
            safety_result.reason_codes
        )

        if (
            conflict_result.status
            == ConflictStatus.REVIEW_REQUIRED
            and final_status
            != SafetyStatus.BLOCKED
        ):
            final_status = SafetyStatus.RESTRICTED
            reason_codes.append(
                "GUIDELINE_REVIEW_REQUIRED"
            )

        if final_status == SafetyStatus.PENDING:
            final_status = (
                SafetyStatus.VALIDATION_FAILED
            )
            reason_codes.append(
                "SAFETY_VALIDATION_INCOMPLETE"
            )

        reason_codes = list(
            dict.fromkeys(reason_codes)
        )

        if final_status in {
            SafetyStatus.BLOCKED,
            SafetyStatus.VALIDATION_FAILED,
        }:
            guide_content = (
                self._build_blocked_content()
            )
        else:
            guide_content = (
                guide_result.guide_content
            )

        return guide_result.model_copy(
            update={
                "guide_content": guide_content,
                "safety_status": final_status,
                "safety_reason_codes": (
                    reason_codes
                ),
            },
            deep=True,
        )

    @staticmethod
    def _build_blocked_content(
    ) -> RecoveryGuideContent:
        return RecoveryGuideContent(
            safety_notice=(
                "안전성 검사를 통과하지 못해 "
                "현재 안내를 제공할 수 없습니다. "
                "의료진 또는 의료기관에 문의하세요."
            )
        )
