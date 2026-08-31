from __future__ import annotations

from datetime import datetime

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
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import InteractionReviewStatus
from app.models.interactions import InteractionRule
from scripts.approve_interaction_rules import (
    InteractionApprovalError,
    approve_staging_dataset,
)
from scripts.import_interaction_staging import (
    InteractionStagingDataset,
    import_staging_dataset,
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


def build_candidate(
    *,
    right_name: str = "아스피린",
    right_code: str = "D000002",
) -> InteractionRuleCandidate:
    return InteractionRuleCandidate(
        dataset_version="interaction-pilot-v1",
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="케토롤락",
            source_code="D000001",
        ),
        right_entity=InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name=right_name,
            source_code=right_code,
        ),
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        effect_summaries=["중증의 위장관계 이상반응 위험"],
        source_records=[
            InteractionSourceRecord(
                source_id="mfds_drug_records",
                document_id="mfds-dur-contraindication",
                record_id=right_code,
                raw_effect_text="중증의 위장관계 이상반응 위험",
            )
        ],
    )


def build_dataset(
    candidates: list[InteractionRuleCandidate],
) -> InteractionStagingDataset:
    return InteractionStagingDataset(
        dataset_version="interaction-pilot-v1",
        generation_id="generation-1",
        candidates=candidates,
        ready_for_rdb_import=False,
        candidate_sha256="a" * 64,
    )


@pytest.mark.asyncio
async def test_approval_is_idempotent_for_exact_staging_generation(
    initialized_db: None,
) -> None:
    dataset = build_dataset([build_candidate()])
    await import_staging_dataset(dataset)

    first = await approve_staging_dataset(
        dataset,
        expected_generation_id="generation-1",
        expected_candidate_sha256="a" * 64,
        reviewer="local-developer",
        approved_at=datetime(2026, 8, 31, 10, 0),
    )
    second = await approve_staging_dataset(
        dataset,
        expected_generation_id="generation-1",
        expected_candidate_sha256="a" * 64,
        reviewer="local-developer",
        approved_at=datetime(2026, 8, 31, 10, 5),
    )

    rule = await InteractionRule.get()
    assert first.approved_count == 1
    assert first.newly_approved_count == 1
    assert second.approved_count == 1
    assert second.newly_approved_count == 0
    assert second.approved_at == first.approved_at
    assert rule.review_status == InteractionReviewStatus.APPROVED
    assert rule.approved_at.replace(tzinfo=None) == datetime(2026, 8, 31, 10, 0)


@pytest.mark.asyncio
async def test_approval_rolls_back_when_database_has_extra_candidate(
    initialized_db: None,
) -> None:
    expected = build_candidate()
    extra = build_candidate(
        right_name="이부프로펜",
        right_code="D000003",
    )
    await upsert_candidates([expected, extra])
    dataset = build_dataset([expected])

    with pytest.raises(InteractionApprovalError, match="건수"):
        await approve_staging_dataset(
            dataset,
            expected_generation_id="generation-1",
            expected_candidate_sha256="a" * 64,
            reviewer="local-developer",
        )

    statuses = await InteractionRule.all().values_list(
        "review_status",
        flat=True,
    )
    assert statuses == [
        InteractionReviewStatus.PENDING,
        InteractionReviewStatus.PENDING,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("generation_id", "candidate_sha256", "message"),
    [
        ("wrong-generation", "a" * 64, "generation_id"),
        ("generation-1", "b" * 64, "SHA-256"),
    ],
)
async def test_approval_rejects_unexpected_generation_or_hash(
    initialized_db: None,
    generation_id: str,
    candidate_sha256: str,
    message: str,
) -> None:
    dataset = build_dataset([build_candidate()])
    await import_staging_dataset(dataset)

    with pytest.raises(InteractionApprovalError, match=message):
        await approve_staging_dataset(
            dataset,
            expected_generation_id=generation_id,
            expected_candidate_sha256=candidate_sha256,
            reviewer="local-developer",
        )

    rule = await InteractionRule.get()
    assert rule.review_status == InteractionReviewStatus.PENDING
