from types import SimpleNamespace

import pytest_asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from tortoise import Tortoise

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
