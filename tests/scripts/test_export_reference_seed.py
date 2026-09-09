from pathlib import Path

import pytest

from app.core.db.reference_seed import REFERENCE_TABLE_ORDER, iter_seed_rows
from scripts.export_reference_seed import export_reference_seed


class FakeExportDb:
    def __init__(self, rows: dict[str, list[dict[str, object]]]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    async def execute_query_dict(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        table = next(name for name in REFERENCE_TABLE_ORDER if f"/* {name} */" in query)
        if "COUNT(*) AS source_count" in query:
            return [{"source_count": len(self.rows.get(table, []))}]
        return [dict(row) for row in self.rows.get(table, [])]


@pytest.mark.asyncio
async def test_export_is_deterministic_and_redacts_admin_secret(tmp_path: Path) -> None:
    db = FakeExportDb(
        {
            "common_code_groups": [
                {
                    "id": 7,
                    "category": "CHL",
                    "group_code": "BDG_TYPE",
                    "group_name": "배지유형",
                    "description": None,
                    "is_active": 1,
                    "created_at": None,
                    "updated_at": None,
                    "created_by_admin_id": 9,
                    "updated_by_admin_id": 9,
                }
            ],
            "admin_settings": [
                {
                    "id": 1,
                    "setting_key": "SMTP",
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "smtp_user": "mailer",
                    "smtp_password_enc": "FORBIDDEN_SECRET",
                    "smtp_from_email": "noreply@example.com",
                    "created_at": None,
                    "updated_at": None,
                    "updated_by_admin_id": 9,
                }
            ],
            "interaction_rules": [
                {
                    "id": 1,
                    "pair_key": "A|B",
                    "pair_type": "DRUG_DRUG",
                    "risk_level": "HIGH",
                    "review_status": "APPROVED",
                    "rule_dataset_version": "v1",
                    "extraction_method": "MANUAL",
                    "approved_at": None,
                    "created_at": None,
                    "updated_at": None,
                    "left_entity_id": 1,
                    "right_entity_id": 2,
                }
            ],
        }
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = await export_reference_seed(db, first_dir, "v1")
    second = await export_reference_seed(db, second_dir, "v1")

    assert [table.name for table in first.tables] == list(REFERENCE_TABLE_ORDER)
    assert (first_dir / "manifest.json").read_bytes() == (second_dir / "manifest.json").read_bytes()
    for table in first.tables:
        assert (first_dir / table.file).read_bytes() == (second_dir / table.file).read_bytes()
    admin_rows = list(iter_seed_rows(first_dir / "admin_settings.jsonl.gz"))
    assert admin_rows[0]["smtp_password_enc"] is None
    assert admin_rows[0]["updated_by_admin_id"] is None
    assert b"FORBIDDEN_SECRET" not in b"".join(path.read_bytes() for path in first_dir.iterdir())
    assert first == second

    query_text = "\n".join(db.queries)
    assert "t.`is_active` = 1" in query_text
    assert "t.`review_status` = 'APPROVED'" in query_text
    assert "t.`is_displayed` = 1" in query_text
    assert "t.`is_deleted` = 0" in query_text
