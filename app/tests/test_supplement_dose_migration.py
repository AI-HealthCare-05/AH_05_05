"""Offline migration guards. Run directly with Python; never connects to a database."""

import ast
import base64
import copy
import json
import unittest
import zlib
from pathlib import Path

MIGRATIONS = Path(__file__).parents[1] / "core/db/migrations/models"


def snapshot(filename: str) -> dict:
    tree = ast.parse((MIGRATIONS / filename).read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(target, "id", None) == "MODELS_STATE" for target in node.targets)
    )
    return json.loads(zlib.decompress(base64.b64decode(ast.literal_eval(assignment.value))))


class SupplementDoseMigrationTests(unittest.TestCase):
    def test_snapshot_preserves_existing_models_and_adds_registration_relation(self) -> None:
        previous = snapshot("29_20260905164657_dose_care_episode.py")
        current = snapshot("30_20260905173000_add_supplement_doses.py")
        self.assertEqual(set(current) - set(previous), {"models.SupplementDose"})
        existing = copy.deepcopy(current)
        del existing["models.SupplementDose"]
        relations = existing["models.UserSupplementNutrient"]["backward_fk_fields"]
        relation = next(field for field in relations if field["name"] == "doses")
        self.assertEqual(relation["python_type"], "models.SupplementDose")
        relations.remove(relation)
        self.assertEqual(existing, previous)

    def test_record_identity_is_registration_date_slot(self) -> None:
        dose = snapshot("30_20260905173000_add_supplement_doses.py")["models.SupplementDose"]
        self.assertEqual(dose["table"], "supplement_doses")
        self.assertEqual(dose["unique_together"], [["registration", "dose_date", "slot"]])
        self.assertEqual(dose["fk_fields"][0]["python_type"], "models.UserSupplementNutrient")
        self.assertEqual(dose["fk_fields"][0]["on_delete"], "CASCADE")

    def test_upgrade_only_creates_new_table_and_never_wipes_existing_data(self) -> None:
        tree = ast.parse((MIGRATIONS / "30_20260905173000_add_supplement_doses.py").read_text(encoding="utf-8"))
        upgrade = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "upgrade")
        sql = ast.literal_eval(upgrade.body[0].value)
        self.assertIn("CREATE TABLE IF NOT EXISTS `supplement_doses`", sql)
        self.assertIn("(`registration_id`, `dose_date`, `slot`)", sql)
        self.assertIn("REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE", sql)
        for statement in ("DROP ", "TRUNCATE ", "DELETE FROM ", "UPDATE ", "ALTER "):
            self.assertNotIn(statement, sql.upper())


if __name__ == "__main__":
    unittest.main()
