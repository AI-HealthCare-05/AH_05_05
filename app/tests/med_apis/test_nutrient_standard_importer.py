import pytest
from tortoise.contrib.test import TestCase

from app.models.supplement_nutrients import NutrientStandard
from scripts.import_nutrient_standards import (
    DEFAULT_PATH,
    parse_csv,
    upsert_records,
    verify_stored_records,
)


class TestNutrientStandardImport(TestCase):
    async def test_upsert_is_idempotent_and_preserves_every_source_key(
        self,
    ) -> None:
        records = parse_csv(DEFAULT_PATH)[:2]

        first = await upsert_records(records)
        second = await upsert_records(records)

        assert (first.total, first.created, first.updated) == (2, 2, 0)
        assert (second.total, second.created, second.updated) == (2, 0, 2)
        assert await NutrientStandard.all().count() == 2

    async def test_verification_rejects_a_missing_source_key(self) -> None:
        records = parse_csv(DEFAULT_PATH)[:2]
        await upsert_records(records)
        await NutrientStandard.filter(
            grp=records[0]["grp"],
            age=records[0]["age"],
        ).delete()

        with pytest.raises(RuntimeError, match="원본 키"):
            await verify_stored_records(records)
