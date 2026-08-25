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
)
