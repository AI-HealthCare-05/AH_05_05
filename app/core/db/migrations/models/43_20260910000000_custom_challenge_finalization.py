"""#315: persist custom challenge final results and badge awards."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `custom_challenge_participations`
            ADD COLUMN `reward_badge_id` BIGINT NULL COMMENT '참여 당시 맞춤 챌린지 보상 배지 ID',
            ADD COLUMN `target_count` INT NOT NULL DEFAULT 0,
            ADD COLUMN `completed_count` INT NOT NULL DEFAULT 0,
            ADD COLUMN `progress_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
            ADD COLUMN `completed_at` DATETIME(6) NULL,
            ADD COLUMN `finalized_at` DATETIME(6) NULL,
            ADD INDEX `idx_custom_participation_reward_badge` (`reward_badge_id`),
            ADD CONSTRAINT `fk_custom_participations_reward_badge`
                FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT;

        UPDATE `custom_challenge_participations` AS participation
        JOIN `custom_challenge_templates` AS template
          ON template.`id` = participation.`template_id`
        SET participation.`reward_badge_id` = template.`reward_badge_id`
        WHERE participation.`reward_badge_id` IS NULL
          AND template.`reward_badge_id` IS NOT NULL;

        ALTER TABLE `custom_challenge_occurrences`
            ADD COLUMN `is_completed` BOOL NOT NULL DEFAULT 0;

        CREATE TABLE `custom_challenge_badge_awards` (
            `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `user_id` BIGINT NOT NULL,
            `badge_id` BIGINT NOT NULL,
            `participation_id` BIGINT NOT NULL,
            `badge_name` VARCHAR(100) NOT NULL,
            `badge_image_path` VARCHAR(500) NOT NULL,
            `awarded_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            CONSTRAINT `fk_custom_badge_awards_user`
                FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_custom_badge_awards_badge`
                FOREIGN KEY (`badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_custom_badge_awards_participation`
                FOREIGN KEY (`participation_id`) REFERENCES `custom_challenge_participations` (`id`) ON DELETE RESTRICT,
            UNIQUE KEY `uq_custom_badge_award_participation_badge` (`participation_id`, `badge_id`),
            KEY `idx_custom_badge_award_user_awarded` (`user_id`, `awarded_at`),
            KEY `idx_custom_badge_award_badge` (`badge_id`)
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Remove only schema introduced by migration 43; award rows are lost on rollback."""
    return """
        DROP TABLE IF EXISTS `custom_challenge_badge_awards`;

        ALTER TABLE `custom_challenge_occurrences`
            DROP COLUMN `is_completed`;

        ALTER TABLE `custom_challenge_participations`
            DROP FOREIGN KEY `fk_custom_participations_reward_badge`,
            DROP INDEX `idx_custom_participation_reward_badge`,
            DROP COLUMN `reward_badge_id`,
            DROP COLUMN `target_count`,
            DROP COLUMN `completed_count`,
            DROP COLUMN `progress_rate`,
            DROP COLUMN `completed_at`,
            DROP COLUMN `finalized_at`;
    """


# This compact literal contains the five finalized model descriptions changed since
# immutable migration 42 (including User/Badge/Participation backwards relations).
# It is intentionally not generated from runtime application models during import.
_CHANGED_MODELS_STATE = "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"

_state = deepcopy(
    decompress_dict(
        import_module("app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads").MODELS_STATE
    )
)
_state.update(decompress_dict(_CHANGED_MODELS_STATE))
MODELS_STATE = compress_dict(_state)
