from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI

from app.apis.v1.med_router import med_router
from app.models.supplement_nutrients import SupplementNutrient
from app.repositories.supplement_nutrient_repository import SupplementNutrientRepository
from app.services.supplement_nutrients import SupplementNutrientService


class StubReviewRepository:
    async def list_excluded_registration_ids(self) -> list[int]:
        return []


class RecordingQuery:
    def __init__(self) -> None:
        self.orderings: tuple[str, ...] | None = None
        self.offset_value: int | None = None
        self.limit_value: int | None = None

    async def count(self) -> int:
        return 0

    def annotate(self, **_annotations: Any) -> "RecordingQuery":
        return self

    def order_by(self, *orderings: str) -> "RecordingQuery":
        self.orderings = orderings
        return self

    def offset(self, value: int) -> "RecordingQuery":
        self.offset_value = value
        return self

    def limit(self, value: int) -> "RecordingQuery":
        self.limit_value = value
        return self

    def __await__(self) -> Generator[None, None, list[SupplementNutrient]]:
        async def resolve() -> list[SupplementNutrient]:
            return []

        return resolve().__await__()


class RecordingRepository:
    def __init__(self) -> None:
        self.search_args: tuple[str, str, str | None, int, int] | None = None

    async def search(
        self,
        name: str,
        *,
        sort: str,
        direction: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[SupplementNutrient], int]:
        self.search_args = (name, sort, direction, offset, limit)
        return [], 0


@pytest.mark.parametrize(
    ("sort", "direction", "expected_orderings"),
    [
        ("name", None, ("name", "id")),
        ("registered", None, ("-registration_count", "id")),
        ("rating", None, ("-rating_average", "-review_count", "id")),
        ("reviews", None, ("-review_count", "-rating_average", "id")),
        ("name", "asc", ("name", "id")),
        ("name", "desc", ("-name", "id")),
        ("registered", "asc", ("registration_count", "id")),
        ("registered", "desc", ("-registration_count", "id")),
        ("rating", "asc", ("rating_average", "review_count", "id")),
        ("rating", "desc", ("-rating_average", "-review_count", "id")),
        ("reviews", "asc", ("review_count", "rating_average", "id")),
        ("reviews", "desc", ("-review_count", "-rating_average", "id")),
    ],
)
async def test_search_applies_requested_direction_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
    sort: str,
    direction: str | None,
    expected_orderings: tuple[str, ...],
) -> None:
    query = RecordingQuery()
    monkeypatch.setattr(SupplementNutrient, "filter", lambda **_filters: query)
    repository = SupplementNutrientRepository(review_repository=StubReviewRepository())

    await repository.search(
        "비타민",
        sort=sort,
        direction=direction,
        offset=20,
        limit=10,
    )

    assert query.orderings == expected_orderings
    assert query.offset_value == 20
    assert query.limit_value == 10


async def test_service_forwards_direction_to_repository() -> None:
    repository = RecordingRepository()
    service = SupplementNutrientService(repository=repository)

    await service.search("  비타민  ", sort="reviews", direction="asc", offset=20, limit=10)

    assert repository.search_args == ("비타민", "reviews", "asc", 20, 10)


def test_search_direction_is_a_validated_query_enum() -> None:
    schema_app = FastAPI()
    schema_app.include_router(med_router, prefix="/api/v1")
    operation = schema_app.openapi()["paths"]["/api/v1/med/nutr"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    direction_schema = parameters["direction"]["schema"]
    enum_values = direction_schema.get("enum")
    if enum_values is None:
        enum_values = next(option["enum"] for option in direction_schema["anyOf"] if "enum" in option)

    assert enum_values == ["asc", "desc"]
