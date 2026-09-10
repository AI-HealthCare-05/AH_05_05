"""Run with the project's disposable MySQL test database, never a development DB."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from tortoise.contrib.test import TestCase

from app.core.db.reference_seed import apply_reference_seed
from app.models.challenges import Badge, Challenge, UserBadge, UserChallenge
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.users import User

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "reference_seed" / "v1"


class TestReferenceSeedMySQL(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.seed_dir = Path(self.enterContext(TemporaryDirectory()))
        # Keep the real, checksum-validated challenge seed and its complete FK graph.
        # Unrelated medical reference rows belong to separate loader/export tests.
        manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
        tables = {"common_code_groups", "common_codes", "badges", "custom_challenge_templates", "challenges"}
        manifest["tables"] = [table for table in manifest["tables"] if table["name"] in tables]
        for table in manifest["tables"]:
            shutil.copyfile(SEED_DIR / table["file"], self.seed_dir / table["file"])
        (self.seed_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    async def test_loader_seeds_empty_database_and_repeats_safely(self) -> None:
        db = Challenge._meta.db

        first = await apply_reference_seed(db, self.seed_dir)
        assert first.tables["challenges"].created == 2
        challenges_before = await Challenge.all().order_by("id").values()
        assert len(challenges_before) == 2
        assert await CommonCode.all().count() > 0
        assert await Badge.all().count() > 0

        repeated = await apply_reference_seed(db, self.seed_dir)

        assert await Challenge.all().order_by("id").values() == challenges_before
        assert repeated.total_created == 0
        assert repeated.tables["challenges"].unchanged == 2
        assert repeated.tables["challenges"].skipped == 0

    async def test_loader_preserves_conflicting_challenges_and_linked_history(self) -> None:
        group = await CommonCodeGroup.create(category="TEST", group_code="SEED411", group_name="기존 코드")
        code = await CommonCode.create(group=group, detail_code="KEEP", detail_name="보존")
        badge = await Badge.create(name="기존 사용자 배지", image_path="/existing-badge.png")
        user = await User.create(email="seed411@example.com", hashed_password="unused", name="시드 테스트")
        for identifier in (2, 3):
            challenge = await Challenge.create(
                id=identifier,
                name=f"기존 챌린지 {identifier}",
                phrase="기존 문구",
                description="기존 설정 보존",
                recruit_start_at=datetime(2026, 8, 1),
                recruit_end_at=datetime(2026, 8, 31),
                challenge_type=code,
                challenge_period=code,
                check_type=code,
                check_frequency=code,
                reward_badge=badge,
            )
            participation = await UserChallenge.create(
                user=user,
                challenge=challenge,
                started_at=datetime(2026, 8, 1),
                end_at=datetime(2026, 8, 7),
                target_count=7,
                completed_count=7,
                progress_rate=100,
            )
            await UserBadge.create(
                user=user,
                badge=badge,
                challenge=challenge,
                user_challenge=participation,
                badge_name=badge.name,
                badge_image_path=badge.image_path,
            )
        challenges_before = await Challenge.all().order_by("id").values()
        participation_before = await UserChallenge.all().order_by("id").values()
        awards_before = await UserBadge.all().order_by("id").values()
        db = Challenge._meta.db

        first = await apply_reference_seed(db, self.seed_dir)
        assert first.tables["challenges"].skipped == 2
        repeated = await apply_reference_seed(db, self.seed_dir)

        assert await Challenge.all().order_by("id").values() == challenges_before
        assert await UserChallenge.all().order_by("id").values() == participation_before
        assert await UserBadge.all().order_by("id").values() == awards_before
        assert repeated.tables["challenges"].skipped == 2
        assert repeated.tables["challenges"].created == 0
        assert repeated.total_created == 0
        assert await CommonCode.all().count() > 1
        assert await Badge.all().count() > 1
