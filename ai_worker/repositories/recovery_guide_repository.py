from decimal import Decimal

from tortoise.backends.base.client import (
    BaseDBAsyncClient,
)
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from ai_worker.schemas.enums import (
    PatientSourceKind as SchemaPatientSourceKind,
)
from ai_worker.schemas.enums import SourceType
from ai_worker.schemas.guide import (
    GuideSource,
    RecoveryGuideResult,
)
from app.models.care import (
    CareAdvice,
    CareEpisode,
    FollowUpVisit,
)
from app.models.enums import (
    CareEpisodeSourceField,
    ChatSafetyStatus,
    GuideSourceType,
    RecoveryGuideStatus,
)
from app.models.enums import (
    PatientSourceKind as OrmPatientSourceKind,
)
from app.models.medications import Medication
from app.models.recovery import (
    RecoveryGuide,
    RecoveryGuideSource,
)


class RecoveryGuideRepository:
    async def save(
        self,
        result: RecoveryGuideResult,
    ) -> int:
        async with in_transaction() as connection:
            for source in result.sources:
                await self._validate_source_ownership(
                    care_episode_id=(result.care_episode_id),
                    source=source,
                    connection=connection,
                )

            recovery_guide = await RecoveryGuide.create(
                care_episode_id=(result.care_episode_id),
                status=(RecoveryGuideStatus.COMPLETED),
                guide_content=(
                    result.guide_content.model_dump(
                        mode="json",
                    )
                ),
                patient_context_hash=(result.patient_context_hash),
                model_name=result.model_name,
                model_version=result.model_version,
                prompt_version=result.prompt_version,
                schema_version=result.schema_version,
                safety_status=ChatSafetyStatus(result.safety_status.value),
                safety_reason_codes=(result.safety_reason_codes),
                completed_at=now(),
                using_db=connection,
            )

            for source in result.sources:
                await self._save_source(
                    recovery_guide_id=(recovery_guide.id),
                    source=source,
                    connection=connection,
                )

        return recovery_guide.id

    @staticmethod
    async def _validate_source_ownership(
        care_episode_id: int,
        source: GuideSource,
        connection: BaseDBAsyncClient,
    ) -> None:
        if source.source_type != SourceType.PATIENT_SAVED_FIELD:
            return

        source_kind = source.patient_source_kind

        if source_kind == SchemaPatientSourceKind.CARE_EPISODE_FIELD:
            return

        belongs_to_episode = False

        if source_kind == SchemaPatientSourceKind.MEDICATION:
            belongs_to_episode = await (
                Medication.filter(
                    id=source.medication_id,
                    care_episode_id=care_episode_id,
                )
                .using_db(connection)
                .exists()
            )

        elif source_kind == SchemaPatientSourceKind.CARE_ADVICE:
            belongs_to_episode = await (
                CareAdvice.filter(
                    id=source.care_advice_id,
                    care_episode_id=care_episode_id,
                )
                .using_db(connection)
                .exists()
            )

        elif source_kind == SchemaPatientSourceKind.FOLLOW_UP_VISIT:
            care_episode = await CareEpisode.filter(id=care_episode_id).using_db(connection).only("user_id").first()
            if care_episode is not None:
                belongs_to_episode = await (
                    FollowUpVisit.filter(
                        id=source.follow_up_visit_id,
                        user_id=care_episode.user_id,
                    )
                    .using_db(connection)
                    .exists()
                )

        if not belongs_to_episode:
            raise ValueError("환자 출처가 현재 사용자 또는 케어 에피소드에 속하지 않습니다.")

    @staticmethod
    async def _save_source(
        recovery_guide_id: int,
        source: GuideSource,
        connection: BaseDBAsyncClient,
    ) -> None:
        patient_source_kind = None
        if source.patient_source_kind is not None:
            patient_source_kind = OrmPatientSourceKind(source.patient_source_kind.value)

        patient_field = None
        if source.patient_field is not None:
            patient_field = CareEpisodeSourceField(source.patient_field.value)

        similarity_score = None
        if source.similarity_score is not None:
            similarity_score = Decimal(str(source.similarity_score))

        await RecoveryGuideSource.create(
            recovery_guide_id=recovery_guide_id,
            source_type=GuideSourceType(source.source_type.value),
            patient_source_kind=patient_source_kind,
            patient_field=patient_field,
            medication_id=source.medication_id,
            care_advice_id=source.care_advice_id,
            follow_up_visit_id=(source.follow_up_visit_id),
            public_dataset_key=(source.public_dataset_key),
            dataset_version=source.dataset_version,
            vector_chunk_id=source.vector_chunk_id,
            source_record_key=source.source_record_key,
            source_field=source.source_field,
            chunk_type=source.chunk_type,
            source_title=source.source_title,
            source_organization=(source.source_organization),
            source_url=source.source_url,
            source_page_number=(source.source_page_number),
            source_license=source.source_license,
            similarity_score=similarity_score,
            citation_order=source.citation_order,
            using_db=connection,
        )
