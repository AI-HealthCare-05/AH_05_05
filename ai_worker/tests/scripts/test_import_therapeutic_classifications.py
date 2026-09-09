from datetime import UTC, datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import InteractionEntityKind, InteractionReviewStatus
from app.models.interactions import (
    InteractionEntity,
    InteractionEntityTherapeuticClass,
    TherapeuticClass,
    TherapeuticClassAlias,
)


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_importer_upserts_reviewed_therapeutic_classification_dataset(
    initialized_db: None,
    tmp_path,
) -> None:
    from scripts.import_therapeutic_classifications import (
        import_therapeutic_classification_dataset,
        load_therapeutic_classification_dataset,
    )

    await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="와파린",
        normalized_name="와파린",
    )
    dataset_path = tmp_path / "therapeutic_classes.yaml"
    dataset_path.write_text(
        """
schema_version: therapeutic-classification-dataset-v1
dataset_version: therapeutic-class-v1
classes:
  - code: ANTICOAGULANT
    display_name: 항응고제
    aliases:
      - 항응고제
      - 혈액응고와 관련된 약
    assignments:
      - entity_kind: DRUG
        canonical_name: 와파린
        review_status: APPROVED
        source_id: kpicia_pharm_review
        document_id: kpicia_pharm_review-c4ea8e68b35b65b3
        record_id: chunk-1
        raw_classification_text: 와파린은 비타민 K 의존성 응혈인자를 저해하여 항응고작용을 한다.
        approved_at: 2026-09-09T09:30:00
""".strip(),
        encoding="utf-8",
    )

    dataset = load_therapeutic_classification_dataset(dataset_path)
    result = await import_therapeutic_classification_dataset(dataset)

    assert result == {
        "dataset_version": "therapeutic-class-v1",
        "class_count": 1,
        "alias_count": 2,
        "assignment_count": 1,
        "approved_assignment_count": 1,
    }
    therapeutic_class = await TherapeuticClass.get(code="ANTICOAGULANT")
    assert await TherapeuticClassAlias.filter(therapeutic_class=therapeutic_class).count() == 2
    assignment = await InteractionEntityTherapeuticClass.get(
        therapeutic_class=therapeutic_class,
    )
    assert assignment.review_status == InteractionReviewStatus.APPROVED
    assert assignment.approved_at == datetime(2026, 9, 9, 9, 30, tzinfo=UTC)
