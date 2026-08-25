import json
from pathlib import Path

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    InteractionRiskLevel,
    InteractionRuleCandidate,
    InteractionSourceRecord,
)
from ai_worker.schemas.interaction import (
    InteractionReviewStatus as SchemaInteractionReviewStatus,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import InteractionReviewStatus
from app.models.interactions import (
    InteractionEntityIdentifier,
    InteractionRule,
    InteractionRuleSource,
)
from scripts.import_interaction_staging import (
    ImportValidationError,
    InteractionStagingDataset,
    import_staging_dataset,
    load_staging_dataset,
    upsert_candidates,
)


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


def build_candidate() -> InteractionRuleCandidate:
    return InteractionRuleCandidate(
        dataset_version="interaction-pilot-v1",
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="와파린",
            source_code="D000001",
        ),
        right_entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="아스피린",
            source_code="D000002",
        ),
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        effect_summaries=["출혈 위험이 증가할 수 있음"],
        source_records=[
            InteractionSourceRecord(
                source_id="mfds_drug_records",
                document_id="mfds-dur-contraindication",
                record_id="100",
                raw_effect_text="출혈 위험이 증가할 수 있음",
            )
        ],
    )


def write_staging(
    root: Path,
    *,
    ready_for_rdb_import: bool = False,
) -> Path:
    version = "interaction-pilot-v1"
    generation = "generation-1"
    generation_dir = root / "staging" / version / generation
    generation_dir.mkdir(parents=True)
    candidate_path = generation_dir / "interaction_rule_candidates.jsonl"
    candidate_path.write_text(
        build_candidate().model_dump_json() + "\n",
        encoding="utf-8",
    )
    quality_path = generation_dir / "interaction-staging-quality.json"
    quality_path.write_text(
        json.dumps(
            {
                "generation_id": generation,
                "dataset_version": version,
                "candidate_count": 1,
                "candidates_path": str(candidate_path.relative_to(root)),
                "quality_report_path": str((generation_dir / "interaction-staging-quality.json").relative_to(root)),
                "ready_for_rdb_import": ready_for_rdb_import,
            }
        ),
        encoding="utf-8",
    )
    marker_path = root / "staging" / version / "current.json"
    marker_path.write_text(
        json.dumps(
            {
                "generation_id": generation,
                "dataset_version": version,
                "candidates_path": str(candidate_path.relative_to(root)),
                "quality_report_path": str(quality_path.relative_to(root)),
            }
        ),
        encoding="utf-8",
    )
    return marker_path


def test_load_staging_requires_explicit_pending_permission(
    tmp_path: Path,
) -> None:
    marker_path = write_staging(tmp_path)

    with pytest.raises(ImportValidationError, match="allow-pending"):
        load_staging_dataset(
            marker_path=marker_path,
            allow_pending=False,
        )


def test_load_staging_validates_current_generation(tmp_path: Path) -> None:
    marker_path = write_staging(tmp_path)

    dataset = load_staging_dataset(
        marker_path=marker_path,
        allow_pending=True,
    )

    assert dataset.dataset_version == "interaction-pilot-v1"
    assert dataset.generation_id == "generation-1"
    assert len(dataset.candidates) == 1


def test_load_staging_rejects_marker_outside_processed_root(
    tmp_path: Path,
) -> None:
    marker_path = write_staging(tmp_path)

    with pytest.raises(ImportValidationError, match="current marker"):
        load_staging_dataset(
            marker_path=marker_path,
            allow_pending=True,
            processed_root=tmp_path / "other",
        )


@pytest.mark.asyncio
async def test_upsert_candidates_is_idempotent_and_keeps_pending(
    initialized_db: None,
) -> None:
    candidates = [build_candidate()]

    first = await upsert_candidates(candidates)
    second = await upsert_candidates(candidates)

    assert first.entities_created == 2
    assert first.identifiers_created == 2
    assert first.rules_created == 1
    assert first.sources_created == 1
    assert second.total_created == 0
    assert await InteractionRule.all().count() == 1
    assert await InteractionRuleSource.all().count() == 1
    assert await InteractionEntityIdentifier.all().count() == 2
    rule = await InteractionRule.first()
    assert rule is not None
    assert rule.review_status == InteractionReviewStatus.PENDING


@pytest.mark.asyncio
async def test_upsert_candidates_does_not_overwrite_review_status(
    initialized_db: None,
) -> None:
    candidate = build_candidate()
    await upsert_candidates([candidate])
    rule = await InteractionRule.get(
        pair_key=candidate.pair_key,
        rule_dataset_version=candidate.dataset_version,
    )
    rule.review_status = InteractionReviewStatus.APPROVED
    await rule.save(update_fields=["review_status"])

    await upsert_candidates([candidate])

    await rule.refresh_from_db()
    assert rule.review_status == InteractionReviewStatus.APPROVED


@pytest.mark.asyncio
async def test_upsert_candidates_rejects_changed_immutable_version(
    initialized_db: None,
) -> None:
    candidate = build_candidate()
    await upsert_candidates([candidate])
    changed = candidate.model_copy(update={"risk_level": InteractionRiskLevel.CAUTION})

    with pytest.raises(ImportValidationError, match="불변"):
        await upsert_candidates([changed])


@pytest.mark.asyncio
async def test_upsert_candidates_rejects_non_pending_candidate(
    initialized_db: None,
) -> None:
    candidate = build_candidate().model_copy(
        update={
            "review_status": SchemaInteractionReviewStatus.APPROVED,
        }
    )

    with pytest.raises(ImportValidationError, match="PENDING"):
        await upsert_candidates([candidate])


@pytest.mark.asyncio
async def test_upsert_candidates_rejects_ambiguous_identifier_source(
    initialized_db: None,
) -> None:
    candidate = build_candidate()
    other_source = InteractionSourceRecord(
        source_id="other_source",
        document_id="other-document",
        record_id="other-record",
        raw_effect_text="다른 출처 설명",
    )
    candidate = candidate.model_copy(
        update={
            "source_records": [
                *candidate.source_records,
                other_source,
            ]
        }
    )

    with pytest.raises(ImportValidationError, match="source_id"):
        await upsert_candidates([candidate])


@pytest.mark.asyncio
async def test_upsert_candidates_rejects_invalid_batch_size(
    initialized_db: None,
) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        await upsert_candidates([build_candidate()], batch_size=0)


@pytest.mark.asyncio
async def test_import_staging_dataset_rolls_back_on_count_mismatch(
    initialized_db: None,
) -> None:
    existing = build_candidate().model_copy(
        update={"dataset_version": "interaction-pilot-v1"},
    )
    await upsert_candidates([existing])
    candidate = build_candidate().model_copy(
        update={
            "dataset_version": "interaction-pilot-v1",
            "right_entity": InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name="이부프로펜",
                source_code="D000003",
            ),
        }
    )
    candidate = InteractionRuleCandidate.model_validate(
        candidate.model_dump(),
    )
    dataset = InteractionStagingDataset(
        dataset_version="interaction-pilot-v1",
        generation_id="generation-2",
        candidates=[candidate],
        ready_for_rdb_import=False,
    )

    with pytest.raises(RuntimeError, match="건수가.*일치하지"):
        await import_staging_dataset(dataset)

    assert await InteractionRule.all().count() == 1
    assert await InteractionRuleSource.all().count() == 1
    assert await InteractionEntityIdentifier.all().count() == 2
