from ai_worker.schemas.enums import (
    ConflictStatus,
)
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import (
    ConflictCheckResult,
)


class RuleBasedGuidelineConflictResolver:
    async def resolve(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[
            RetrievedGuidelineChunk
        ],
    ) -> ConflictCheckResult:
        if not guideline_chunks:
            return ConflictCheckResult(
                status=(
                    ConflictStatus.NOT_APPLICABLE
                ),
                reason=(
                    "검사할 공공 가이드라인이 없습니다."
                ),
            )

        patient_instruction_topics = {
            instruction.instruction_type.value.upper()
            for instruction
            in patient_context.instructions
        }

        if not patient_instruction_topics:
            return ConflictCheckResult(
                status=ConflictStatus.NO_CONFLICT,
                usable_guideline_chunks=(
                    guideline_chunks
                ),
                reason=(
                    "비교할 환자 확정 지침이 없습니다."
                ),
            )

        usable_chunks: list[
            RetrievedGuidelineChunk
        ] = []
        excluded_chunks: list[
            RetrievedGuidelineChunk
        ] = []
        has_missing_topic = False

        for chunk in guideline_chunks:
            topic = chunk.metadata.topic

            if topic is None or not topic.strip():
                excluded_chunks.append(chunk)
                has_missing_topic = True
                continue

            normalized_topic = topic.strip().upper()

            if (
                normalized_topic
                in patient_instruction_topics
            ):
                excluded_chunks.append(chunk)
                continue

            usable_chunks.append(chunk)

        if has_missing_topic:
            return ConflictCheckResult(
                status=(
                    ConflictStatus.REVIEW_REQUIRED
                ),
                usable_guideline_chunks=usable_chunks,
                excluded_guideline_chunks=(
                    excluded_chunks
                ),
                reason=(
                    "주제 정보가 없는 공공자료는 "
                    "환자 지침과의 충돌 여부를 "
                    "자동으로 판단할 수 없습니다."
                ),
            )

        if not excluded_chunks:
            return ConflictCheckResult(
                status=ConflictStatus.NO_CONFLICT,
                usable_guideline_chunks=usable_chunks,
                reason=(
                    "환자 지침과 동일한 주제의 "
                    "공공자료가 없습니다."
                ),
            )

        if not usable_chunks:
            return ConflictCheckResult(
                status=(
                    ConflictStatus
                    .PUBLIC_SOURCE_EXCLUDED
                ),
                excluded_guideline_chunks=(
                    excluded_chunks
                ),
                reason=(
                    "환자 확정 지침과 동일한 "
                    "주제의 공공자료를 제외했습니다."
                ),
            )

        return ConflictCheckResult(
            status=(
                ConflictStatus.PATIENT_DATA_PRIORITY
            ),
            usable_guideline_chunks=usable_chunks,
            excluded_guideline_chunks=(
                excluded_chunks
            ),
            reason=(
                "환자 확정 지침을 우선 적용하고 "
                "동일 주제의 공공자료를 제외했습니다."
            ),
        )
