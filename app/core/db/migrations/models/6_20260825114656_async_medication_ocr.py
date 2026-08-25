from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_structured_status`;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_structured_status` CHECK (`structured_result` IS NULL OR `status` IN ('READY_FOR_REVIEW', 'COMPLETE'));
        ALTER TABLE `care_episodes` DROP FOREIGN KEY `fk_care_episode_source_ocr`;
        ALTER TABLE `ocr_jobs` DROP INDEX `uid_ocr_jobs_care_ep_11f3f7`;
        ALTER TABLE `ocr_jobs` DROP FOREIGN KEY `fk_ocr_jobs_care_epi_5d7af6f9`;
        ALTER TABLE `ocr_jobs` ADD `user_id` BIGINT NULL;
        UPDATE `ocr_jobs` AS `job`
        INNER JOIN `care_episodes` AS `episode` ON `episode`.`id` = `job`.`care_episode_id`
        SET `job`.`user_id` = `episode`.`user_id`
        WHERE `job`.`user_id` IS NULL;
        UPDATE `ocr_jobs` AS `job`
        INNER JOIN (
            SELECT `id`, `duplicate_rank`
            FROM (
                SELECT
                    `id`,
                    ROW_NUMBER() OVER (
                        PARTITION BY `user_id`, `idempotency_key`
                        ORDER BY `id`
                    ) AS `duplicate_rank`
                FROM `ocr_jobs`
            ) AS `ranked_source`
        ) AS `ranked` ON `ranked`.`id` = `job`.`id`
        SET `job`.`idempotency_key` = CONCAT(
            'm6-', `job`.`id`, '-', LEFT(SHA2(`job`.`idempotency_key`, 256), 64)
        )
        WHERE `ranked`.`duplicate_rank` > 1;
        ALTER TABLE `ocr_jobs` MODIFY COLUMN `user_id` BIGINT NOT NULL;
        ALTER TABLE `ocr_jobs` MODIFY COLUMN `care_episode_id` BIGINT NULL;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `fk_ocr_jobs_care_epi_5d7af6f9` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE SET NULL;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `fk_ocr_jobs_user_33066343` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
        ALTER TABLE `ocr_jobs` ADD UNIQUE INDEX `uid_ocr_jobs_user_id_825f43` (`user_id`, `idempotency_key`);
        ALTER TABLE `care_episodes` ADD CONSTRAINT `fk_care_episode_source_ocr` FOREIGN KEY (`source_ocr_job_id`, `id`) REFERENCES `ocr_jobs` (`id`, `care_episode_id`) ON DELETE RESTRICT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `ocr_jobs` SET `structured_result` = NULL WHERE `status` = 'COMPLETE';
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_structured_status`;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_structured_status` CHECK (`structured_result` IS NULL OR `status` = 'READY_FOR_REVIEW');
        ALTER TABLE `ocr_jobs` DROP FOREIGN KEY `fk_ocr_jobs_user_33066343`;
        ALTER TABLE `ocr_jobs` DROP INDEX `uid_ocr_jobs_user_id_825f43`;
        DELETE FROM `ocr_jobs` WHERE `care_episode_id` IS NULL;
        ALTER TABLE `ocr_jobs` DROP COLUMN `user_id`;
        ALTER TABLE `care_episodes` DROP FOREIGN KEY `fk_care_episode_source_ocr`;
        ALTER TABLE `ocr_jobs` DROP FOREIGN KEY `fk_ocr_jobs_care_epi_5d7af6f9`;
        ALTER TABLE `ocr_jobs` MODIFY COLUMN `care_episode_id` BIGINT NOT NULL;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `fk_ocr_jobs_care_epi_5d7af6f9` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE;
        ALTER TABLE `ocr_jobs` ADD UNIQUE INDEX `uid_ocr_jobs_care_ep_11f3f7` (`care_episode_id`, `idempotency_key`);
        ALTER TABLE `care_episodes` ADD CONSTRAINT `fk_care_episode_source_ocr` FOREIGN KEY (`source_ocr_job_id`, `id`) REFERENCES `ocr_jobs` (`id`, `care_episode_id`) ON DELETE RESTRICT;"""


MODELS_STATE = (
    "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"
    "s63cQ="
)
