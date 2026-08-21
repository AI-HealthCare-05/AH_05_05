from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `medications` ADD CONSTRAINT `chk_v4_up_medication_days_guard` CHECK (`days` IS NULL OR `days` BETWEEN 1 AND 365);

        ALTER TABLE `admin` ADD `session_salt` VARCHAR(32) NULL;
        UPDATE `admin` SET `session_salt` = MD5(CONCAT(RAND(), `id`, NOW(6))) WHERE `session_salt` IS NULL;
        ALTER TABLE `admin` MODIFY COLUMN `session_salt` VARCHAR(32) NOT NULL;

        ALTER TABLE `user_settings` ADD `terms_agreed_at` DATETIME(6) NULL;
        ALTER TABLE `user_settings` ADD `notify_consented_at` DATETIME(6) NULL;
        CREATE TABLE IF NOT EXISTS `user_notify_histories` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `setting_key` VARCHAR(20) NOT NULL COMMENT 'IS_NOTIFY_MEDICATION: IS_NOTIFY_MEDICATION\nIS_NOTIFY_SCHEDULE: IS_NOTIFY_SCHEDULE\nIS_NOTIFY_GUIDE: IS_NOTIFY_GUIDE',
    `new_value` BOOL NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_user_not_user_d9e48ebe` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_user_notify_user_id_57bbb4` (`user_id`, `setting_key`, `created_at`),
    KEY `idx_user_notify_created_4f3fde` (`created_at`)
) CHARACTER SET utf8mb4;

        ALTER TABLE `chat_sessions` ADD `user_id` BIGINT NULL;
        UPDATE `chat_sessions` AS `cs`
        INNER JOIN `care_episodes` AS `ce` ON `ce`.`id` = `cs`.`care_episode_id`
        SET `cs`.`user_id` = `ce`.`user_id`
        WHERE `cs`.`user_id` IS NULL;
        ALTER TABLE `chat_sessions` MODIFY COLUMN `user_id` BIGINT NOT NULL;
        ALTER TABLE `chat_sessions` ADD CONSTRAINT `fk_chat_ses_user_91ae8bac` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_sessions` MODIFY COLUMN `care_episode_id` BIGINT NULL;

        ALTER TABLE `care_advices` ADD `category` VARCHAR(11) NULL COMMENT 'ACTIVITY: ACTIVITY\nHYGIENE: HYGIENE\nDIET: DIET\nLIFESTYLE: LIFESTYLE\nRESTRICTION: RESTRICTION\nRED_FLAG: RED_FLAG\nOTHER: OTHER';
        UPDATE `care_advices` SET `category` = 'OTHER' WHERE `category` IS NULL;
        ALTER TABLE `care_advices` MODIFY COLUMN `category` VARCHAR(11) NOT NULL COMMENT 'ACTIVITY: ACTIVITY\nHYGIENE: HYGIENE\nDIET: DIET\nLIFESTYLE: LIFESTYLE\nRESTRICTION: RESTRICTION\nRED_FLAG: RED_FLAG\nOTHER: OTHER';
        ALTER TABLE `care_advices` ADD INDEX `idx_care_advice_care_ep_64ac23` (`care_episode_id`, `category`);

        ALTER TABLE `medications` ADD `efficacy` VARCHAR(500) NULL;
        ALTER TABLE `medications` ADD `administration` VARCHAR(500) NULL;
        ALTER TABLE `medications` ADD `precautions` VARCHAR(500) NULL;
        ALTER TABLE `medications` MODIFY COLUMN `note` VARCHAR(500) NULL;
        ALTER TABLE `medications` DROP CHECK `chk_medications_days`;
        ALTER TABLE `medications` ADD CONSTRAINT `chk_medications_days` CHECK (`days` IS NULL OR `days` BETWEEN 1 AND 365);
        ALTER TABLE `medications` DROP CHECK `chk_v4_up_medication_days_guard`;

        ALTER TABLE `follow_up_visits` ADD `visit_date` DATE NULL;
        ALTER TABLE `follow_up_visits` ADD `visit_time` TIME(6) NULL;
        ALTER TABLE `follow_up_visits` ADD `source_ocr_job_id` BIGINT NULL;
        UPDATE `follow_up_visits`
        SET `visit_date` = DATE(`visit_at`), `visit_time` = TIME(`visit_at`)
        WHERE `visit_date` IS NULL;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `visit_date` DATE NOT NULL;
        ALTER TABLE `follow_up_visits` DROP INDEX `idx_follow_up_v_visit_a_8be3c7`;
        ALTER TABLE `follow_up_visits` DROP COLUMN `visit_at`;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `department` VARCHAR(255) NULL;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `doctor_name` VARCHAR(255) NULL;
        ALTER TABLE `follow_up_visits` ADD CONSTRAINT `fk_follow_u_ocr_jobs_7673fb70` FOREIGN KEY (`source_ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE SET NULL;
        ALTER TABLE `follow_up_visits` ADD INDEX `idx_follow_up_v_visit_d_dbbd94` (`visit_date`, `visit_time`, `id`);

        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_medicati_64a4e67a`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_medicati_64a4e67a` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_care_adv_48d68054`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_care_adv_48d68054` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_follow_u_ffd61594`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_follow_u_ffd61594` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_medicati_89e5d700`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_medicati_89e5d700` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_care_adv_d6cc90e0`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_care_adv_d6cc90e0` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_follow_u_53b251cd`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_follow_u_53b251cd` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE RESTRICT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TEMPORARY TABLE IF EXISTS `_aerich_v4_downgrade_guard`;
        CREATE TEMPORARY TABLE `_aerich_v4_downgrade_guard` (
    `id` TINYINT NOT NULL PRIMARY KEY,
    `chat_care_episode_ok` BOOL NOT NULL,
    `follow_department_ok` BOOL NOT NULL,
    `follow_doctor_ok` BOOL NOT NULL,
    `medication_note_ok` BOOL NOT NULL,
    CONSTRAINT `chk_v4_down_chat_care_episode` CHECK (`chat_care_episode_ok` = 1),
    CONSTRAINT `chk_v4_down_follow_department` CHECK (`follow_department_ok` = 1),
    CONSTRAINT `chk_v4_down_follow_doctor` CHECK (`follow_doctor_ok` = 1),
    CONSTRAINT `chk_v4_down_medication_note` CHECK (`medication_note_ok` = 1)
) ENGINE=InnoDB;
        INSERT INTO `_aerich_v4_downgrade_guard`
            (`id`, `chat_care_episode_ok`, `follow_department_ok`, `follow_doctor_ok`, `medication_note_ok`)
        SELECT
            1,
            NOT EXISTS (
                SELECT 1 FROM `chat_sessions` WHERE `care_episode_id` IS NULL
            ),
            NOT EXISTS (
                SELECT 1
                FROM `follow_up_visits`
                WHERE `department` IS NOT NULL AND CHAR_LENGTH(`department`) > 100
            ),
            NOT EXISTS (
                SELECT 1
                FROM `follow_up_visits`
                WHERE `doctor_name` IS NOT NULL AND CHAR_LENGTH(`doctor_name`) > 100
            ),
            NOT EXISTS (
                SELECT 1
                FROM `medications`
                WHERE `note` IS NOT NULL AND CHAR_LENGTH(`note`) > 255
            );

        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_follow_u_53b251cd`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_follow_u_53b251cd` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_care_adv_d6cc90e0`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_care_adv_d6cc90e0` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_medicati_89e5d700`;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_medicati_89e5d700` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_follow_u_ffd61594`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_follow_u_ffd61594` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_care_adv_48d68054`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_care_adv_48d68054` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_medicati_64a4e67a`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_medicati_64a4e67a` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE;

        ALTER TABLE `follow_up_visits` DROP INDEX `idx_follow_up_v_visit_d_dbbd94`;
        ALTER TABLE `follow_up_visits` DROP FOREIGN KEY `fk_follow_u_ocr_jobs_7673fb70`;
        ALTER TABLE `follow_up_visits` ADD `visit_at` DATETIME(6) NULL;
        UPDATE `follow_up_visits`
        SET `visit_at` = TIMESTAMP(`visit_date`, COALESCE(`visit_time`, '00:00:00'))
        WHERE `visit_at` IS NULL;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `visit_at` DATETIME(6) NOT NULL;
        ALTER TABLE `follow_up_visits` DROP COLUMN `source_ocr_job_id`;
        ALTER TABLE `follow_up_visits` DROP COLUMN `visit_time`;
        ALTER TABLE `follow_up_visits` DROP COLUMN `visit_date`;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `department` VARCHAR(100) NULL;
        ALTER TABLE `follow_up_visits` MODIFY COLUMN `doctor_name` VARCHAR(100) NULL;
        ALTER TABLE `follow_up_visits` ADD INDEX `idx_follow_up_v_visit_a_8be3c7` (`visit_at`);

        ALTER TABLE `medications` DROP CHECK `chk_medications_days`;
        ALTER TABLE `medications` ADD CONSTRAINT `chk_medications_days` CHECK (`days` IS NULL OR `days` >= 1);
        ALTER TABLE `medications` MODIFY COLUMN `note` VARCHAR(255) NULL;
        ALTER TABLE `medications` DROP COLUMN `precautions`;
        ALTER TABLE `medications` DROP COLUMN `administration`;
        ALTER TABLE `medications` DROP COLUMN `efficacy`;

        ALTER TABLE `care_advices` DROP INDEX `idx_care_advice_care_ep_64ac23`;
        ALTER TABLE `care_advices` DROP COLUMN `category`;

        ALTER TABLE `chat_sessions` MODIFY COLUMN `care_episode_id` BIGINT NOT NULL;
        ALTER TABLE `chat_sessions` DROP FOREIGN KEY `fk_chat_ses_user_91ae8bac`;
        ALTER TABLE `chat_sessions` DROP COLUMN `user_id`;

        DROP TABLE IF EXISTS `user_notify_histories`;
        ALTER TABLE `user_settings` DROP COLUMN `notify_consented_at`;
        ALTER TABLE `user_settings` DROP COLUMN `terms_agreed_at`;

        ALTER TABLE `admin` DROP COLUMN `session_salt`;

        DROP TEMPORARY TABLE `_aerich_v4_downgrade_guard`;"""


MODELS_STATE = (
    "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"
    "ewWSA9I8xLNuGKgmlTdlSvlrnJ//D0WENxo="
)
