from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `medication_safety_rules` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `rule_key` VARCHAR(64) NOT NULL,
    `rule_type` VARCHAR(26) NOT NULL COMMENT 'PREGNANCY_CONTRAINDICATION: PREGNANCY_CONTRAINDICATION\nAGE_CONTRAINDICATION: AGE_CONTRAINDICATION\nELDERLY_CAUTION: ELDERLY_CAUTION\nDOSE_CAUTION: DOSE_CAUTION\nDURATION_CAUTION: DURATION_CAUTION\nDAILY_MAX_DOSE: DAILY_MAX_DOSE\nEXCIPIENT_CAUTION: EXCIPIENT_CAUTION',
    `risk_level` VARCHAR(15) NOT NULL COMMENT 'CONTRAINDICATED: CONTRAINDICATED\nHIGH_CAUTION: HIGH_CAUTION\nCAUTION: CAUTION\nINFORMATIONAL: INFORMATIONAL\nUNKNOWN: UNKNOWN',
    `guidance_text` LONGTEXT NOT NULL,
    `review_status` VARCHAR(8) NOT NULL COMMENT 'PENDING: PENDING\nAPPROVED: APPROVED\nREJECTED: REJECTED' DEFAULT 'PENDING',
    `rule_dataset_version` VARCHAR(100) NOT NULL,
    `extraction_method` VARCHAR(24) NOT NULL COMMENT 'DETERMINISTIC_STRUCTURED: DETERMINISTIC_STRUCTURED\nMANUAL_ANNOTATION: MANUAL_ANNOTATION',
    `approved_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `interaction_entity_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__rule_ke_aed585` (`rule_key`, `rule_dataset_version`),
    CONSTRAINT `fk_medicati_interact_b6577fa6` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `chk_med_safety_rule_key` CHECK (CHAR_LENGTH(`rule_key`) = 64 AND `rule_key` REGEXP '^[0-9A-Fa-f]{64}$'),
    CONSTRAINT `chk_med_safety_rule_approval` CHECK ((`review_status` = 'APPROVED' AND `approved_at` IS NOT NULL) OR (`review_status` <> 'APPROVED' AND `approved_at` IS NULL)),
    KEY `idx_medication__interac_4bdad9` (`interaction_entity_id`, `rule_type`, `review_status`),
    KEY `idx_medication__rule_da_2e2c4a` (`rule_dataset_version`, `review_status`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_safety_rule_conditions` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `condition_group_no` SMALLINT NOT NULL,
    `condition_order` SMALLINT NOT NULL,
    `condition_kind` VARCHAR(20) NOT NULL COMMENT 'PREGNANCY_STATUS: PREGNANCY_STATUS\nAGE_DAYS: AGE_DAYS\nAGE_YEARS: AGE_YEARS\nDAILY_DOSE: DAILY_DOSE\nDURATION_DAYS: DURATION_DAYS\nDOSAGE_FORM: DOSAGE_FORM\nADMINISTRATION_ROUTE: ADMINISTRATION_ROUTE\nEXCIPIENT_PRESENT: EXCIPIENT_PRESENT',
    `comparison_operator` VARCHAR(7) NOT NULL COMMENT 'EQ: EQ\nLT: LT\nLTE: LTE\nGT: GT\nGTE: GTE\nBETWEEN: BETWEEN\nPRESENT: PRESENT',
    `value_min` DECIMAL(14,4),
    `value_max` DECIMAL(14,4),
    `value_text` VARCHAR(255),
    `unit` VARCHAR(30),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `medication_safety_rule_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__medicat_a9617b` (`medication_safety_rule_id`, `condition_group_no`, `condition_order`),
    CONSTRAINT `fk_medicati_medicati_463af7e4` FOREIGN KEY (`medication_safety_rule_id`) REFERENCES `medication_safety_rules` (`id`) ON DELETE CASCADE,
    CONSTRAINT `chk_med_safety_condition_order` CHECK (`condition_group_no` >= 1 AND `condition_order` >= 1),
    CONSTRAINT `chk_med_safety_between` CHECK (`comparison_operator` <> 'BETWEEN' OR (`value_min` IS NOT NULL AND `value_max` IS NOT NULL AND `value_min` <= `value_max`)),
    CONSTRAINT `chk_med_safety_numeric_value` CHECK (`comparison_operator` NOT IN ('LT', 'LTE', 'GT', 'GTE') OR `value_min` IS NOT NULL),
    KEY `idx_medication__conditi_280967` (`condition_kind`, `comparison_operator`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_safety_rule_sources` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_id` VARCHAR(100) NOT NULL,
    `document_id` VARCHAR(150) NOT NULL,
    `record_id` VARCHAR(150) NOT NULL,
    `raw_effect_text` LONGTEXT NOT NULL,
    `source_published_at` DATE,
    `source_url` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `medication_safety_rule_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__medicat_5a46d3` (`medication_safety_rule_id`, `source_id`, `document_id`, `record_id`),
    CONSTRAINT `fk_medicati_medicati_25d1957c` FOREIGN KEY (`medication_safety_rule_id`) REFERENCES `medication_safety_rules` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__source__e6d97f` (`source_id`, `record_id`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_patient_source`;
        ALTER TABLE `chat_message_sources` ADD `medication_safety_rule_id` BIGINT;
        ALTER TABLE `chat_message_sources` MODIFY COLUMN `source_type` VARCHAR(22) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK\nUSER_SUPPLEMENT: USER_SUPPLEMENT\nINTERACTION_RULE: INTERACTION_RULE\nMEDICATION_SAFETY_RULE: MEDICATION_SAFETY_RULE';
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_medicati_99016ea2` FOREIGN KEY (`medication_safety_rule_id`) REFERENCES `medication_safety_rules` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_medicat_5900ca` (`medication_safety_rule_id`);
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_patient_source` CHECK ((`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `care_episode_id` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))) OR (`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL) OR (`source_type` = 'USER_SUPPLEMENT' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NOT NULL AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL) OR (`source_type` = 'INTERACTION_RULE' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NOT NULL AND `medication_safety_rule_id` IS NULL) OR (`source_type` = 'MEDICATION_SAFETY_RULE' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NOT NULL));"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_patient_source`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_medicat_5900ca`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_medicati_99016ea2`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `medication_safety_rule_id`;
        ALTER TABLE `chat_message_sources` MODIFY COLUMN `source_type` VARCHAR(19) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK\nUSER_SUPPLEMENT: USER_SUPPLEMENT\nINTERACTION_RULE: INTERACTION_RULE';
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_patient_source` CHECK ((`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `care_episode_id` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))) OR (`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL) OR (`source_type` = 'USER_SUPPLEMENT' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NOT NULL AND `interaction_rule_id` IS NULL) OR (`source_type` = 'INTERACTION_RULE' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NOT NULL));
        DROP TABLE IF EXISTS `medication_safety_rule_conditions`;
        DROP TABLE IF EXISTS `medication_safety_rule_sources`;
        DROP TABLE IF EXISTS `medication_safety_rules`;"""


MODELS_STATE = (
    "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"
)
