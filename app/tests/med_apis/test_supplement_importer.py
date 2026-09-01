from tortoise.contrib.test import TestCase

from app.models.supplement_nutrients import SupplementNutrient
from scripts.import_supplement_nutrients import (
    upsert_records,
    validate_rows,
    verify_stored_records,
)
from tests.scripts.test_import_supplement_nutrients import valid_row


class TestSupplementNutrientUpsert(TestCase):
    async def test_upsert_is_re_runnable_and_updates_existing_products(self) -> None:
        records = validate_rows(
            [
                valid_row("F101-UPSERT-001", "철분 A"),
                valid_row("F101-UPSERT-002", "철분 B"),
            ],
            first_row_number=3,
        )

        first = await upsert_records(records, batch_size=1)
        records[0]["name"] = "철분 A 수정"
        second = await upsert_records(records, batch_size=1)

        assert (first.total, first.created, first.updated, first.failed) == (2, 2, 0, 0)
        assert (second.total, second.created, second.updated, second.failed) == (2, 0, 2, 0)
        assert await SupplementNutrient.all().count() == 2
        assert (await SupplementNutrient.get(food_code="F101-UPSERT-001")).name == "철분 A 수정"

    async def test_verify_stored_records_rejects_missing_source_codes(self) -> None:
        records = validate_rows(
            [valid_row("F101-MISSING-001", "누락 검증")],
            first_row_number=3,
        )

        with self.assertRaisesRegex(RuntimeError, "원본 식품코드"):
            await verify_stored_records(records)
