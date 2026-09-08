from types import SimpleNamespace

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from tortoise import Tortoise

from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_search import (
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.supplement_nutrients import SupplementNutrient


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


class StaticSupplementCatalog:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    async def list_names(self) -> list[str]:
        return self._names


class FailingSupplementCatalog:
    async def list_names(self) -> list[str]:
        raise RuntimeError("Qdrant unavailable")

    async def list_entries(self) -> list[object]:
        raise RuntimeError("Qdrant unavailable")


async def test_db_catalog_reads_unique_supplement_names(
    initialized_db: None,
) -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        DbSupplementIngredientCatalog,
    )

    common = {
        "basis_qty": "500mg",
        "energy_kcal": 0,
        "protein_g": "0.00",
        "carb_g": "0.00",
        "serving_desc": "1정",
        "serving_size": "500mg",
        "daily_freq": "1회",
    }
    await SupplementNutrient.create(
        food_code="SUP-1",
        name="비타민 K",
        **common,
    )
    await SupplementNutrient.create(
        food_code="SUP-2",
        name="  루테인  ",
        **common,
    )

    assert await DbSupplementIngredientCatalog().list_names() == [
        "루테인",
        "비타민 K",
    ]


async def test_qdrant_catalog_reads_unique_names_from_active_dataset() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        QdrantSupplementIngredientCatalog,
    )

    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="knowledge_release",
        vectors_config=models.VectorParams(
            size=2,
            distance=models.Distance.COSINE,
        ),
    )
    await client.upsert(
        collection_name="knowledge_release",
        points=[
            models.PointStruct(
                id=1,
                vector=[1.0, 0.0],
                payload={
                    "metadata": {
                        "dataset_version": "knowledge-v2",
                        "ingredient_names": ["비타민 K", "루테인"],
                    }
                },
            ),
            models.PointStruct(
                id=2,
                vector=[0.0, 1.0],
                payload={
                    "metadata": {
                        "dataset_version": "knowledge-v2",
                        "ingredient_names": ["비타민 K", "  루테인  "],
                    }
                },
            ),
            models.PointStruct(
                id=3,
                vector=[0.5, 0.5],
                payload={
                    "metadata": {
                        "dataset_version": "knowledge-v1",
                        "ingredient_names": ["비타민 D"],
                    }
                },
            ),
        ],
        wait=True,
    )
    catalog = QdrantSupplementIngredientCatalog(
        client=client,
        collection_name="knowledge_release",
        dataset_version="knowledge-v2",
    )

    try:
        assert await catalog.list_names() == ["루테인", "비타민 K"]
    finally:
        await client.close()


async def test_qdrant_catalog_preserves_metadata_entity_types() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        QdrantSupplementIngredientCatalog,
    )

    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="knowledge_typed_release",
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    await client.upsert(
        collection_name="knowledge_typed_release",
        points=[
            models.PointStruct(
                id=1,
                vector=[1.0, 0.0],
                payload={
                    "metadata": {
                        "dataset_version": "knowledge-v2",
                        "product_names": ["검증제품"],
                        "drug_names": ["검증약성분"],
                        "ingredient_names": ["검증영양성분"],
                        "food_names": ["검증음식"],
                    }
                },
            )
        ],
        wait=True,
    )
    catalog = QdrantSupplementIngredientCatalog(
        client=client,
        collection_name="knowledge_typed_release",
        dataset_version="knowledge-v2",
    )

    try:
        entries = await catalog.list_entries()
    finally:
        await client.close()

    assert [(entry.canonical_name, entry.entity_type, entry.kind, entry.source) for entry in entries] == [
        (
            "검증약성분",
            MedicationQueryEntityType.INGREDIENT_NAME,
            InteractionEntityKind.DRUG,
            MedicationQueryEntitySource.QDRANT,
        ),
        (
            "검증영양성분",
            MedicationQueryEntityType.INGREDIENT_NAME,
            InteractionEntityKind.SUPPLEMENT,
            MedicationQueryEntitySource.QDRANT,
        ),
        (
            "검증음식",
            MedicationQueryEntityType.FOOD_CATEGORY,
            InteractionEntityKind.FOOD,
            MedicationQueryEntitySource.QDRANT,
        ),
        (
            "검증제품",
            MedicationQueryEntityType.PRODUCT_NAME,
            InteractionEntityKind.DRUG,
            MedicationQueryEntitySource.QDRANT,
        ),
    ]


async def test_qdrant_catalog_prefers_typed_entries_and_preserves_aliases() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        QdrantSupplementIngredientCatalog,
    )

    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="knowledge_typed_alias_release",
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    await client.upsert(
        collection_name="knowledge_typed_alias_release",
        points=[
            models.PointStruct(
                id=1,
                vector=[1.0, 0.0],
                payload={
                    "metadata": {
                        "dataset_version": "knowledge-v6",
                        # 기존 평면 필드는 v5 하위호환용이며, v6에서는
                        # 정식명·별칭·타입을 담은 계약을 우선 사용한다.
                        "food_names": ["과일주스"],
                        "entity_catalog_entries": [
                            {
                                "canonical_name": "과일주스",
                                "aliases": ["과일주스", "자몽주스"],
                                "entity_type": "FOOD_CATEGORY",
                                "kind": "FOOD",
                            }
                        ],
                    }
                },
            )
        ],
        wait=True,
    )
    catalog = QdrantSupplementIngredientCatalog(
        client=client,
        collection_name="knowledge_typed_alias_release",
        dataset_version="knowledge-v6",
    )

    try:
        entries = await catalog.list_entries()
    finally:
        await client.close()

    assert len(entries) == 1
    assert entries[0].canonical_name == "과일주스"
    assert entries[0].aliases == ["과일주스", "자몽주스"]
    assert entries[0].entity_type == MedicationQueryEntityType.FOOD_CATEGORY
    assert entries[0].kind == InteractionEntityKind.FOOD
    assert entries[0].source == MedicationQueryEntitySource.QDRANT


async def test_composite_catalog_keeps_rdb_names_when_qdrant_fails() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        CompositeSupplementIngredientCatalog,
    )

    catalog = CompositeSupplementIngredientCatalog(
        sources=[
            StaticSupplementCatalog(["마그네슘", "비타민 K"]),
            FailingSupplementCatalog(),
        ]
    )

    assert await catalog.list_names() == ["마그네슘", "비타민 K"]


async def test_composite_catalog_reports_unavailable_when_all_sources_fail() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        CatalogSourcesUnavailableError,
        CompositeSupplementIngredientCatalog,
    )

    catalog = CompositeSupplementIngredientCatalog(
        sources=[FailingSupplementCatalog(), FailingSupplementCatalog()],
    )

    with pytest.raises(CatalogSourcesUnavailableError):
        await catalog.list_entries()


async def test_qdrant_catalog_reuses_cached_names() -> None:
    from ai_worker.repositories.supplement_ingredient_catalog_repository import (
        QdrantSupplementIngredientCatalog,
    )

    client = SimpleNamespace()
    calls = 0

    async def scroll(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return (
            [
                SimpleNamespace(
                    payload={
                        "metadata": {
                            "ingredient_names": ["비타민 K"],
                        }
                    }
                )
            ],
            None,
        )

    client.scroll = scroll
    catalog = QdrantSupplementIngredientCatalog(
        client=client,
        collection_name="knowledge_release",
        dataset_version="knowledge-v2",
        cache_ttl_seconds=300,
    )

    assert await catalog.list_names() == ["비타민 K"]
    assert await catalog.list_names() == ["비타민 K"]
    assert calls == 1
