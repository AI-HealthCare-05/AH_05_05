from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `medications` DROP FOREIGN KEY `fk_medicati_ocr_extr_cb0f373d`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_ocr_extr_ccc3036d`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_extract_282037`;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_ocr_extr_7b3aa9bf`;
        ALTER TABLE `recovery_guide_sources` DROP INDEX `idx_recovery_gu_extract_f6412c`;
        ALTER TABLE `ocr_jobs` DROP INDEX `idempotency_key`;
        ALTER TABLE `ocr_jobs` DROP INDEX `idx_ocr_jobs_content_fee3bc`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_jobs_page_count`;
        ALTER TABLE `follow_up_visits` DROP FOREIGN KEY `fk_follow_u_ocr_extr_9689a29b`;
        ALTER TABLE `care_advices` DROP FOREIGN KEY `fk_care_adv_ocr_extr_a9606e6c`;
        CREATE TABLE IF NOT EXISTS `user_settings` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `is_notify_medication` BOOL NOT NULL DEFAULT 1,
    `is_notify_schedule` BOOL NOT NULL DEFAULT 1,
    `is_notify_guide` BOOL NOT NULL DEFAULT 1,
    `is_terms_agreed` BOOL NOT NULL DEFAULT 0,
    `morning_medication_time` TIME(6) NOT NULL DEFAULT '08:00:00',
    `lunch_medication_time` TIME(6) NOT NULL DEFAULT '13:00:00',
    `evening_medication_time` TIME(6) NOT NULL DEFAULT '19:00:00',
    `bedtime_medication_time` TIME(6) NOT NULL DEFAULT '22:00:00',
    `user_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_user_set_user_67a93e12` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_slots` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `medication_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__medicat_6c4526` (`medication_id`, `slot`),
    CONSTRAINT `fk_medicati_medicati_556577c2` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__slot_e95579` (`slot`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `user` DROP COLUMN `is_alarm`;
        ALTER TABLE `care_advices` DROP COLUMN `source_extracted_field_id`;
        ALTER TABLE `care_episodes` ADD `surgery` VARCHAR(500);
        ALTER TABLE `care_episodes` ADD `medication_days` INT;
        ALTER TABLE `care_episodes` ADD `source_ocr_job_id` BIGINT;
        ALTER TABLE `care_episodes` ADD `medication_start_slot` VARCHAR(7) COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME';
        ALTER TABLE `care_episodes` ADD `discharge_date` DATE;
        ALTER TABLE `care_episodes` ADD `diagnosis` VARCHAR(500);
        ALTER TABLE `care_episodes` ADD `confirmed_at` DATETIME(6);
        ALTER TABLE `care_episodes` ADD `confirmation_hash` VARCHAR(64);
        ALTER TABLE `care_episodes` ADD `medication_start_date` DATE;
        ALTER TABLE `follow_up_visits` DROP COLUMN `source_extracted_field_id`;
        ALTER TABLE `ocr_jobs` ADD `structuring_model` VARCHAR(100) NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `structured_result` JSON;
        ALTER TABLE `ocr_jobs` ADD `ocr_model` VARCHAR(100) NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `prompt_version` VARCHAR(100) NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `ready_at` DATETIME(6);
        ALTER TABLE `ocr_jobs` ADD `expires_at` DATETIME(6);
        ALTER TABLE `ocr_jobs` ADD `updated_at` DATETIME(6);
        ALTER TABLE `ocr_jobs` ADD `input_manifest` JSON NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `started_at` DATETIME(6);
        ALTER TABLE `ocr_jobs` ADD `schema_version` VARCHAR(50) NOT NULL;
        ALTER TABLE `ocr_jobs` DROP COLUMN `document_type`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `content_hash`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `pipeline_version`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `page_count`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `masking_status`;
        ALTER TABLE `recovery_guide_sources` ADD `care_advice_id` BIGINT;
        ALTER TABLE `recovery_guide_sources` ADD `medication_id` BIGINT;
        ALTER TABLE `recovery_guide_sources` ADD `patient_source_kind` VARCHAR(18) COMMENT 'CARE_EPISODE_FIELD: CARE_EPISODE_FIELD\nMEDICATION: MEDICATION\nCARE_ADVICE: CARE_ADVICE\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT';
        ALTER TABLE `recovery_guide_sources` ADD `patient_field` VARCHAR(15) COMMENT 'DIAGNOSIS: DIAGNOSIS\nSURGERY: SURGERY\nDISCHARGE_DATE: DISCHARGE_DATE\nMEDICATION_DAYS: MEDICATION_DAYS';
        ALTER TABLE `recovery_guide_sources` ADD `follow_up_visit_id` BIGINT;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `extracted_field_id`;
        ALTER TABLE `chat_message_sources` ADD `care_advice_id` BIGINT;
        ALTER TABLE `chat_message_sources` ADD `medication_id` BIGINT;
        ALTER TABLE `chat_message_sources` ADD `patient_source_kind` VARCHAR(18) COMMENT 'CARE_EPISODE_FIELD: CARE_EPISODE_FIELD\nMEDICATION: MEDICATION\nCARE_ADVICE: CARE_ADVICE\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT';
        ALTER TABLE `chat_message_sources` ADD `patient_field` VARCHAR(15) COMMENT 'DIAGNOSIS: DIAGNOSIS\nSURGERY: SURGERY\nDISCHARGE_DATE: DISCHARGE_DATE\nMEDICATION_DAYS: MEDICATION_DAYS';
        ALTER TABLE `chat_message_sources` ADD `follow_up_visit_id` BIGINT;
        ALTER TABLE `chat_message_sources` DROP COLUMN `extracted_field_id`;
        ALTER TABLE `alarms` ADD `meal_slot` VARCHAR(7) COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME';
        ALTER TABLE `alarms` ALTER COLUMN `alarm_type` SET DEFAULT 'MEDICATION';
        ALTER TABLE `alarms` MODIFY COLUMN `alarm_type` VARCHAR(15) NOT NULL COMMENT 'MEDICATION: MEDICATION\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT\nGUIDE_CHECK: GUIDE_CHECK' DEFAULT 'MEDICATION';
        ALTER TABLE `background_jobs` ADD `idempotency_key` VARCHAR(150) NOT NULL UNIQUE;
        ALTER TABLE `medications` DROP COLUMN `source_extracted_field_id`;
        DROP TABLE IF EXISTS `medication_times`;
        DROP TABLE IF EXISTS `user_consents`;
        DROP TABLE IF EXISTS `ocr_extracted_fields`;
        ALTER TABLE `ocr_jobs` ADD UNIQUE INDEX `uid_ocr_jobs_care_ep_11f3f7` (`care_episode_id`, `idempotency_key`);
        ALTER TABLE `ocr_jobs` ADD UNIQUE INDEX `uid_ocr_jobs_id_d66b71` (`id`, `care_episode_id`);
        ALTER TABLE `ocr_jobs` ADD INDEX `idx_ocr_jobs_expires_c6acd3` (`expires_at`);
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_follow_u_ffd61594` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_medicati_64a4e67a` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_care_adv_48d68054` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE CASCADE;
        ALTER TABLE `recovery_guide_sources` ADD INDEX `idx_recovery_gu_care_ad_37b577` (`care_advice_id`);
        ALTER TABLE `recovery_guide_sources` ADD INDEX `idx_recovery_gu_medicat_48bd28` (`medication_id`);
        ALTER TABLE `recovery_guide_sources` ADD INDEX `idx_recovery_gu_follow__ac2980` (`follow_up_visit_id`);
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_follow_u_53b251cd` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_medicati_89e5d700` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_care_adv_d6cc90e0` FOREIGN KEY (`care_advice_id`) REFERENCES `care_advices` (`id`) ON DELETE CASCADE;
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_care_ad_c38653` (`care_advice_id`);
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_medicat_f9e61f` (`medication_id`);
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_follow__c69f37` (`follow_up_visit_id`);
        ALTER TABLE `alarms` ADD UNIQUE INDEX `uid_alarms_user_id_e74d92` (`user_id`, `alarm_type`, `meal_slot`);
        ALTER TABLE `care_episodes` ADD CONSTRAINT `fk_care_episode_source_ocr` FOREIGN KEY (`source_ocr_job_id`, `id`) REFERENCES `ocr_jobs` (`id`, `care_episode_id`) ON DELETE RESTRICT;
        ALTER TABLE `care_episodes` ADD CONSTRAINT `chk_care_medication_days` CHECK (`medication_days` IS NULL OR (`medication_days` BETWEEN 1 AND 365));
        ALTER TABLE `care_episodes` ADD CONSTRAINT `chk_care_confirmation` CHECK ((`source_ocr_job_id` IS NULL AND `confirmed_at` IS NULL AND `confirmation_hash` IS NULL) OR (`source_ocr_job_id` IS NOT NULL AND `confirmed_at` IS NOT NULL AND `confirmation_hash` IS NOT NULL));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_structured_status` CHECK (`structured_result` IS NULL OR `status` = 'READY_FOR_REVIEW');
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_ready_payload` CHECK (`status` <> 'READY_FOR_REVIEW' OR (`structured_result` IS NOT NULL AND `ready_at` IS NOT NULL AND `expires_at` IS NOT NULL));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_error_code` CHECK ((`status` = 'FAILED' AND `error_code` IS NOT NULL AND `error_code` IN ('OCR_PROVIDER_ERROR', 'OCR_PROVIDER_TIMEOUT', 'EXTRACTION_FAILED', 'VALIDATION_FAILED', 'WORKER_INTERRUPTED')) OR (`status` = 'CANCELLED' AND `error_code` IS NOT NULL AND `error_code` IN ('USER_CANCELLED', 'REVIEW_EXPIRED')) OR (`status` IN ('QUEUED', 'PROCESSING', 'READY_FOR_REVIEW', 'COMPLETE') AND `error_code` IS NULL));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_completed_at` CHECK ((`status` IN ('COMPLETE', 'FAILED', 'CANCELLED') AND `completed_at` IS NOT NULL) OR (`status` IN ('QUEUED', 'PROCESSING', 'READY_FOR_REVIEW') AND `completed_at` IS NULL));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_status_timestamps` CHECK ((`status` = 'QUEUED' AND `started_at` IS NULL AND `ready_at` IS NULL AND `expires_at` IS NULL) OR (`status` = 'PROCESSING' AND `started_at` IS NOT NULL AND `ready_at` IS NULL AND `expires_at` IS NULL) OR (`status` = 'READY_FOR_REVIEW' AND `started_at` IS NOT NULL AND `ready_at` IS NOT NULL AND `expires_at` IS NOT NULL) OR (`status` IN ('COMPLETE', 'FAILED') AND `started_at` IS NOT NULL AND `ready_at` IS NULL AND `expires_at` IS NULL) OR (`status` = 'CANCELLED' AND `ready_at` IS NULL AND `expires_at` IS NULL));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_started_at` CHECK (`started_at` IS NULL OR `started_at` >= `created_at`);
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_ready_at` CHECK (`ready_at` IS NULL OR (`started_at` IS NOT NULL AND `ready_at` >= `started_at`));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_completed_order` CHECK (`completed_at` IS NULL OR `completed_at` >= COALESCE(`started_at`, `created_at`));
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_expires_at` CHECK (`expires_at` IS NULL OR `ready_at` IS NULL OR `expires_at` > `ready_at`);
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_patient_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))));
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL AND `source_field` IS NOT NULL AND `chunk_type` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_citation_order` CHECK (`citation_order` >= 1);
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_patient_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL AND `source_field` IS NOT NULL AND `chunk_type` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_citation_order` CHECK (`citation_order` >= 1);
        ALTER TABLE `alarms` ADD CONSTRAINT `chk_alarm_meal_slot` CHECK ((`alarm_type` = 'MEDICATION' AND `meal_slot` IS NOT NULL) OR (`alarm_type` <> 'MEDICATION' AND `meal_slot` IS NULL));
        ALTER TABLE `medications` ADD CONSTRAINT `chk_medication_as_needed_note` CHECK (`times_per_day` IS NOT NULL OR `note` IS NOT NULL);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `medications` DROP CHECK `chk_medication_as_needed_note`;
        ALTER TABLE `alarms` DROP CHECK `chk_alarm_meal_slot`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_citation_order`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_public_source`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_patient_source`;
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_citation_order`;
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_public_source`;
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_patient_source`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_expires_at`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_completed_order`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_ready_at`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_started_at`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_status_timestamps`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_completed_at`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_error_code`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_ready_payload`;
        ALTER TABLE `ocr_jobs` DROP CHECK `chk_ocr_structured_status`;
        ALTER TABLE `care_episodes` DROP CHECK `chk_care_confirmation`;
        ALTER TABLE `care_episodes` DROP CHECK `chk_care_medication_days`;
        ALTER TABLE `care_episodes` DROP FOREIGN KEY `fk_care_episode_source_ocr`;
        ALTER TABLE `recovery_guide_sources` DROP INDEX `idx_recovery_gu_follow__ac2980`;
        ALTER TABLE `recovery_guide_sources` DROP INDEX `idx_recovery_gu_medicat_48bd28`;
        ALTER TABLE `recovery_guide_sources` DROP INDEX `idx_recovery_gu_care_ad_37b577`;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_care_adv_48d68054`;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_medicati_64a4e67a`;
        ALTER TABLE `recovery_guide_sources` DROP FOREIGN KEY `fk_recovery_follow_u_ffd61594`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_follow__c69f37`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_medicat_f9e61f`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_care_ad_c38653`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_care_adv_d6cc90e0`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_medicati_89e5d700`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_follow_u_53b251cd`;
        ALTER TABLE `background_jobs` DROP INDEX `idempotency_key`;
        ALTER TABLE `ocr_jobs` DROP INDEX `idx_ocr_jobs_expires_c6acd3`;
        ALTER TABLE `ocr_jobs` DROP INDEX `uid_ocr_jobs_id_d66b71`;
        ALTER TABLE `ocr_jobs` DROP INDEX `uid_ocr_jobs_care_ep_11f3f7`;
        ALTER TABLE `alarms` DROP INDEX `uid_alarms_user_id_e74d92`;
        ALTER TABLE `user` ADD `is_alarm` BOOL NOT NULL DEFAULT 1;
        ALTER TABLE `alarms` DROP COLUMN `meal_slot`;
        ALTER TABLE `alarms` ALTER COLUMN `alarm_type` SET DEFAULT 'CUSTOM';
        ALTER TABLE `alarms` MODIFY COLUMN `alarm_type` VARCHAR(15) NOT NULL COMMENT 'MEDICATION: MEDICATION\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT\nCUSTOM: CUSTOM' DEFAULT 'CUSTOM';
        ALTER TABLE `ocr_jobs` ADD `document_type` VARCHAR(21) NOT NULL COMMENT 'DISCHARGE_SUMMARY: DISCHARGE_SUMMARY\nDISCHARGE_INSTRUCTION: DISCHARGE_INSTRUCTION\nPRESCRIPTION: PRESCRIPTION\nMEDICATION_GUIDE: MEDICATION_GUIDE\nMEDICATION_BAG: MEDICATION_BAG';
        ALTER TABLE `ocr_jobs` ADD `content_hash` VARCHAR(71) NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `pipeline_version` VARCHAR(50) NOT NULL;
        ALTER TABLE `ocr_jobs` ADD `page_count` INT NOT NULL DEFAULT 1;
        ALTER TABLE `ocr_jobs` ADD `masking_status` VARCHAR(9) NOT NULL COMMENT 'PENDING: PENDING\nCOMPLETED: COMPLETED\nSUSPECTED: SUSPECTED\nFAILED: FAILED' DEFAULT 'PENDING';
        ALTER TABLE `ocr_jobs` DROP COLUMN `structuring_model`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `structured_result`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `ocr_model`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `prompt_version`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `ready_at`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `expires_at`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `updated_at`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `input_manifest`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `started_at`;
        ALTER TABLE `ocr_jobs` DROP COLUMN `schema_version`;
        ALTER TABLE `ocr_jobs` ADD CONSTRAINT `chk_ocr_jobs_page_count` CHECK (`page_count` >= 1);
        CREATE TABLE IF NOT EXISTS `ocr_extracted_fields` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `entity_key` VARCHAR(100) NOT NULL,
    `field_type` VARCHAR(100) NOT NULL,
    `raw_value` LONGTEXT,
    `normalized_value` JSON,
    `reviewed_value` JSON,
    `confidence` DECIMAL(5,4),
    `review_status` VARCHAR(15) NOT NULL COMMENT 'UNREVIEWED: UNREVIEWED\nREVIEW_REQUIRED: REVIEW_REQUIRED\nREVIEWED: REVIEWED' DEFAULT 'UNREVIEWED',
    `source_page` INT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `corrected_at` DATETIME(6),
    `reviewed_at` DATETIME(6),
    `ocr_job_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ocr_extract_ocr_job_79f99e` (`ocr_job_id`, `entity_key`, `field_type`),
    CONSTRAINT `fk_ocr_extr_ocr_jobs_0177fb59` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE CASCADE,
    KEY `idx_ocr_extract_ocr_job_265293` (`ocr_job_id`, `review_status`),
    CONSTRAINT `chk_ocr_fields_confidence` CHECK (`confidence` IS NULL OR `confidence` BETWEEN 0 AND 1),
    CONSTRAINT `chk_ocr_fields_source_page` CHECK (`source_page` IS NULL OR `source_page` >= 1)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_times` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `time_of_day` TIME(6) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `medication_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__medicat_3433ed` (`medication_id`, `time_of_day`),
    CONSTRAINT `fk_medicati_medicati_5ed407e9` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__time_of_e5e9d9` (`time_of_day`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `user_consents` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `consent_type` VARCHAR(12) NOT NULL COMMENT 'MEDICAL_DATA: MEDICAL_DATA\nAI_USAGE: AI_USAGE\nNOTIFICATION: NOTIFICATION',
    `agreed` BOOL NOT NULL,
    `agreed_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `policy_version` VARCHAR(50) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_user_con_user_7f06cdfb` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_user_consen_user_id_e498c8` (`user_id`, `consent_type`, `agreed_at`),
    KEY `idx_user_consen_user_id_9f8412` (`user_id`, `consent_type`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `care_advices` ADD `source_extracted_field_id` BIGINT;
        ALTER TABLE `medications` ADD `source_extracted_field_id` BIGINT;
        ALTER TABLE `care_episodes` DROP COLUMN `surgery`;
        ALTER TABLE `care_episodes` DROP COLUMN `medication_days`;
        ALTER TABLE `care_episodes` DROP COLUMN `source_ocr_job_id`;
        ALTER TABLE `care_episodes` DROP COLUMN `medication_start_slot`;
        ALTER TABLE `care_episodes` DROP COLUMN `discharge_date`;
        ALTER TABLE `care_episodes` DROP COLUMN `diagnosis`;
        ALTER TABLE `care_episodes` DROP COLUMN `confirmed_at`;
        ALTER TABLE `care_episodes` DROP COLUMN `confirmation_hash`;
        ALTER TABLE `care_episodes` DROP COLUMN `medication_start_date`;
        ALTER TABLE `background_jobs` DROP COLUMN `idempotency_key`;
        ALTER TABLE `follow_up_visits` ADD `source_extracted_field_id` BIGINT;
        ALTER TABLE `chat_message_sources` ADD `extracted_field_id` BIGINT;
        ALTER TABLE `chat_message_sources` DROP COLUMN `care_advice_id`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `medication_id`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `patient_source_kind`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `patient_field`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `follow_up_visit_id`;
        ALTER TABLE `recovery_guide_sources` ADD `extracted_field_id` BIGINT;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `care_advice_id`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `medication_id`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `patient_source_kind`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `patient_field`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `follow_up_visit_id`;
        DROP TABLE IF EXISTS `medication_slots`;
        DROP TABLE IF EXISTS `user_settings`;
        ALTER TABLE `ocr_jobs` ADD INDEX `idx_ocr_jobs_content_fee3bc` (`content_hash`);
        ALTER TABLE `ocr_jobs` ADD UNIQUE INDEX `idempotency_key` (`idempotency_key`);
        ALTER TABLE `care_advices` ADD CONSTRAINT `fk_care_adv_ocr_extr_a9606e6c` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL;
        ALTER TABLE `medications` ADD CONSTRAINT `fk_medicati_ocr_extr_cb0f373d` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL;
        ALTER TABLE `follow_up_visits` ADD CONSTRAINT `fk_follow_u_ocr_extr_9689a29b` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_ocr_extr_ccc3036d` FOREIGN KEY (`extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL;
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_extract_282037` (`extracted_field_id`);
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `fk_recovery_ocr_extr_7b3aa9bf` FOREIGN KEY (`extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL;
        ALTER TABLE `recovery_guide_sources` ADD INDEX `idx_recovery_gu_extract_f6412c` (`extracted_field_id`);"""


MODELS_STATE = (
    "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"
    "etkIwJNw/xrAYD0aTyplAof43z6/97rS3R"
)
