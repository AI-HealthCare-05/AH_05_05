from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `interaction_entities` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `entity_kind` VARCHAR(10) NOT NULL COMMENT 'DRUG: DRUG\nSUPPLEMENT: SUPPLEMENT\nFOOD: FOOD',
    `canonical_name` VARCHAR(255) NOT NULL,
    `normalized_name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    UNIQUE KEY `uid_interaction_entity__5a2836` (`entity_kind`, `normalized_name`),
    KEY `idx_interaction_canonic_5a607b` (`canonical_name`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `interaction_entity_aliases` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alias_type` VARCHAR(15) NOT NULL COMMENT 'INGREDIENT_NAME: INGREDIENT_NAME\nPRODUCT_NAME: PRODUCT_NAME\nSYNONYM: SYNONYM\nSOURCE_NAME: SOURCE_NAME',
    `alias` VARCHAR(255) NOT NULL,
    `normalized_alias` VARCHAR(255) NOT NULL,
    `is_preferred` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_entity_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_interac_b09911` (`interaction_entity_id`, `normalized_alias`),
    CONSTRAINT `fk_interact_interact_4db217be` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE CASCADE,
    KEY `idx_interaction_normali_557052` (`normalized_alias`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `interaction_entity_identifiers` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_id` VARCHAR(100) NOT NULL,
    `source_code` VARCHAR(100) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_entity_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_source__faffc7` (`source_id`, `source_code`),
    UNIQUE KEY `uid_interaction_interac_328f17` (`interaction_entity_id`, `source_id`),
    CONSTRAINT `fk_interact_interact_dacb226c` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `interaction_rules` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `pair_key` VARCHAR(64) NOT NULL,
    `pair_type` VARCHAR(21) NOT NULL COMMENT 'DRUG_DRUG: DRUG_DRUG\nDRUG_SUPPLEMENT: DRUG_SUPPLEMENT\nSUPPLEMENT_SUPPLEMENT: SUPPLEMENT_SUPPLEMENT\nDRUG_FOOD: DRUG_FOOD',
    `risk_level` VARCHAR(15) NOT NULL COMMENT 'CONTRAINDICATED: CONTRAINDICATED\nHIGH_CAUTION: HIGH_CAUTION\nCAUTION: CAUTION\nINFORMATIONAL: INFORMATIONAL\nUNKNOWN: UNKNOWN',
    `review_status` VARCHAR(8) NOT NULL COMMENT 'PENDING: PENDING\nAPPROVED: APPROVED\nREJECTED: REJECTED' DEFAULT 'PENDING',
    `rule_dataset_version` VARCHAR(100) NOT NULL,
    `extraction_method` VARCHAR(24) NOT NULL COMMENT 'DETERMINISTIC_STRUCTURED: DETERMINISTIC_STRUCTURED\nMANUAL_ANNOTATION: MANUAL_ANNOTATION',
    `approved_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `left_entity_id` BIGINT NOT NULL,
    `right_entity_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_pair_ke_e31c96` (`pair_key`, `rule_dataset_version`),
    CONSTRAINT `fk_interact_interact_0d5908df` FOREIGN KEY (`left_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_interact_interact_42469a44` FOREIGN KEY (`right_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `chk_interaction_rule_entities` CHECK (`left_entity_id` <> `right_entity_id`),
    CONSTRAINT `chk_interaction_rule_approval` CHECK ((`review_status` = 'APPROVED' AND `approved_at` IS NOT NULL) OR (`review_status` <> 'APPROVED' AND `approved_at` IS NULL)),
    CONSTRAINT `chk_interaction_pair_key` CHECK (CHAR_LENGTH(`pair_key`) = 64 AND `pair_key` REGEXP '^[0-9A-Fa-f]{64}$'),
    KEY `idx_interaction_left_en_64165d` (`left_entity_id`, `right_entity_id`),
    KEY `idx_interaction_pair_ty_e68c87` (`pair_type`, `review_status`, `risk_level`),
    KEY `idx_interaction_rule_da_6c779b` (`rule_dataset_version`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `interaction_rule_sources` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_id` VARCHAR(100) NOT NULL,
    `document_id` VARCHAR(150) NOT NULL,
    `record_id` VARCHAR(150) NOT NULL,
    `raw_effect_text` LONGTEXT NOT NULL,
    `source_published_at` DATE,
    `source_url` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_rule_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_interac_5c3fbe` (`interaction_rule_id`, `source_id`, `document_id`, `record_id`),
    CONSTRAINT `fk_interact_interact_536e7d84` FOREIGN KEY (`interaction_rule_id`) REFERENCES `interaction_rules` (`id`) ON DELETE CASCADE,
    KEY `idx_interaction_source__94997b` (`source_id`, `record_id`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `interaction_rule_evidence_chunks` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `dataset_key` VARCHAR(100) NOT NULL,
    `dataset_version` VARCHAR(100) NOT NULL,
    `vector_chunk_id` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_rule_source_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_interac_082bce` (`interaction_rule_source_id`, `dataset_version`, `vector_chunk_id`),
    CONSTRAINT `fk_interact_interact_164817fe` FOREIGN KEY (`interaction_rule_source_id`) REFERENCES `interaction_rule_sources` (`id`) ON DELETE CASCADE,
    KEY `idx_interaction_vector__d3dbed` (`vector_chunk_id`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_interaction_entities` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `match_method` VARCHAR(11) NOT NULL COMMENT 'SOURCE_CODE: SOURCE_CODE\nEXACT_NAME: EXACT_NAME\nALIAS: ALIAS\nMANUAL: MANUAL',
    `match_confidence` DECIMAL(5,4),
    `matched_source_text` VARCHAR(255) NOT NULL,
    `reviewed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_entity_id` BIGINT NOT NULL,
    `medication_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__medicat_afc57c` (`medication_id`, `interaction_entity_id`),
    CONSTRAINT `fk_medicati_interact_258696dd` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_medicati_medicati_5c310933` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE,
    CONSTRAINT `chk_medication_interaction_confidence` CHECK (`match_confidence` IS NULL OR (`match_confidence` >= 0 AND `match_confidence` <= 1)),
    KEY `idx_medication__interac_95091e` (`interaction_entity_id`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `medication_interaction_mappings` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `mapping_status` VARCHAR(7) NOT NULL COMMENT 'PENDING: PENDING\nMATCHED: MATCHED\nFAILED: FAILED' DEFAULT 'PENDING',
    `error_code` VARCHAR(100),
    `mapped_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `medication_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_medicati_medicati_ffaa3d82` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__mapping_1f609a` (`mapping_status`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `supplement_interaction_entities` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `amount` DECIMAL(12,4),
    `unit` VARCHAR(30),
    `source_field` VARCHAR(100),
    `match_method` VARCHAR(11) NOT NULL COMMENT 'SOURCE_CODE: SOURCE_CODE\nEXACT_NAME: EXACT_NAME\nALIAS: ALIAS\nMANUAL: MANUAL' DEFAULT 'SOURCE_CODE',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `interaction_entity_id` BIGINT NOT NULL,
    `supplement_nutrient_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_supplement__supplem_0192fa` (`supplement_nutrient_id`, `interaction_entity_id`),
    CONSTRAINT `fk_suppleme_interact_0e06396d` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_suppleme_suppleme_e6abfc99` FOREIGN KEY (`supplement_nutrient_id`) REFERENCES `supplement_nutrients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `chk_supplement_interaction_amount` CHECK (`amount` IS NULL OR `amount` > 0),
    CONSTRAINT `chk_supplement_interaction_amount_unit` CHECK ((`amount` IS NULL AND `unit` IS NULL) OR (`amount` IS NOT NULL AND `unit` IS NOT NULL)),
    KEY `idx_supplement__interac_3b410c` (`interaction_entity_id`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `chat_messages` ADD `duration_ms` INT;
        ALTER TABLE `chat_messages` ADD CONSTRAINT `chk_chat_duration_ms` CHECK (`duration_ms` IS NULL OR `duration_ms` >= 0);
        ALTER TABLE `chat_messages` MODIFY COLUMN `route_type` VARCHAR(21) COMMENT 'PATIENT_DB: PATIENT_DB\nPUBLIC_RAG: PUBLIC_RAG\nPATIENT_AND_PUBLIC: PATIENT_AND_PUBLIC\nGENERAL_LIFESTYLE: GENERAL_LIFESTYLE\nINTERACTION: INTERACTION\nSAFETY_RESPONSE: SAFETY_RESPONSE\nOUT_OF_SCOPE_RESPONSE: OUT_OF_SCOPE_RESPONSE';
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_patient_source`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_public_source`;
        ALTER TABLE `chat_message_sources` ADD `user_suppl_nutrient_id` BIGINT;
        ALTER TABLE `chat_message_sources` ADD `care_episode_id` BIGINT;
        ALTER TABLE `chat_message_sources` ADD `interaction_rule_id` BIGINT;
        ALTER TABLE `chat_message_sources` MODIFY COLUMN `source_type` VARCHAR(19) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK\nUSER_SUPPLEMENT: USER_SUPPLEMENT\nINTERACTION_RULE: INTERACTION_RULE';
        UPDATE `chat_message_sources` AS `source`
        INNER JOIN `chat_messages` AS `message` ON `message`.`id` = `source`.`chat_message_id`
        INNER JOIN `chat_sessions` AS `session` ON `session`.`id` = `message`.`chat_session_id`
        SET `source`.`care_episode_id` = `session`.`care_episode_id`
        WHERE `source`.`source_type` = 'PATIENT_SAVED_FIELD'
          AND `source`.`patient_source_kind` = 'CARE_EPISODE_FIELD'
          AND `source`.`care_episode_id` IS NULL;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_user_sup_4624a86e` FOREIGN KEY (`user_suppl_nutrient_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_interact_65e4a78b` FOREIGN KEY (`interaction_rule_id`) REFERENCES `interaction_rules` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `fk_chat_mes_care_epi_e6e04ad2` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE RESTRICT;
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_user_su_360dbe` (`user_suppl_nutrient_id`);
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_interac_8c6fd1` (`interaction_rule_id`);
        ALTER TABLE `chat_message_sources` ADD INDEX `idx_chat_messag_care_ep_a7d8ed` (`care_episode_id`);
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_patient_source` CHECK ((`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `care_episode_id` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))) OR (`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL) OR (`source_type` = 'USER_SUPPLEMENT' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NOT NULL AND `interaction_rule_id` IS NULL) OR (`source_type` = 'INTERACTION_RULE' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NOT NULL));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL) OR (`source_type` <> 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `source_page_number` IS NULL AND `source_license` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_similarity_score` CHECK (`similarity_score` IS NULL OR (`similarity_score` >= 0 AND `similarity_score` <= 1));
        ALTER TABLE `chat_sessions` ADD INDEX `idx_chat_sessio_user_id_5d846b` (`user_id`, `status`, `last_message_at`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_similarity_score`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_public_source`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_patient_source`;
        ALTER TABLE `chat_messages` DROP CHECK `chk_chat_duration_ms`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_care_epi_e6e04ad2`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_interact_65e4a78b`;
        ALTER TABLE `chat_message_sources` DROP FOREIGN KEY `fk_chat_mes_user_sup_4624a86e`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_care_ep_a7d8ed`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_interac_8c6fd1`;
        ALTER TABLE `chat_message_sources` DROP INDEX `idx_chat_messag_user_su_360dbe`;
        ALTER TABLE `chat_sessions` ADD INDEX `fk_chat_ses_user_91ae8bac` (`user_id`);
        ALTER TABLE `chat_sessions` DROP INDEX `idx_chat_sessio_user_id_5d846b`;
        ALTER TABLE `chat_messages` DROP COLUMN `duration_ms`;
        ALTER TABLE `chat_messages` MODIFY COLUMN `route_type` VARCHAR(21) COMMENT 'PATIENT_DB: PATIENT_DB\nPUBLIC_RAG: PUBLIC_RAG\nPATIENT_AND_PUBLIC: PATIENT_AND_PUBLIC\nGENERAL_LIFESTYLE: GENERAL_LIFESTYLE\nSAFETY_RESPONSE: SAFETY_RESPONSE\nOUT_OF_SCOPE_RESPONSE: OUT_OF_SCOPE_RESPONSE';
        DELETE FROM `chat_message_sources` WHERE `source_type` IN ('USER_SUPPLEMENT', 'INTERACTION_RULE');
        ALTER TABLE `chat_message_sources` DROP COLUMN `user_suppl_nutrient_id`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `care_episode_id`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `interaction_rule_id`;
        ALTER TABLE `chat_message_sources` MODIFY COLUMN `source_type` VARCHAR(19) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK';
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_patient_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `patient_source_kind` IS NOT NULL AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD' AND `patient_field` IS NOT NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL AND `medication_id` IS NOT NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'CARE_ADVICE' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NOT NULL AND `follow_up_visit_id` IS NULL) OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL AND `medication_id` IS NULL AND `care_advice_id` IS NULL AND `follow_up_visit_id` IS NOT NULL))));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `source_page_number` IS NULL AND `source_license` IS NULL AND `similarity_score` IS NULL));
        DROP TABLE IF EXISTS `interaction_rule_evidence_chunks`;
        DROP TABLE IF EXISTS `interaction_rule_sources`;
        DROP TABLE IF EXISTS `interaction_rules`;
        DROP TABLE IF EXISTS `medication_interaction_entities`;
        DROP TABLE IF EXISTS `supplement_interaction_entities`;
        DROP TABLE IF EXISTS `medication_interaction_mappings`;
        DROP TABLE IF EXISTS `interaction_entity_aliases`;
        DROP TABLE IF EXISTS `interaction_entity_identifiers`;
        DROP TABLE IF EXISTS `interaction_entities`;"""


MODELS_STATE = (
    "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"
    "o5axtTRKdMofC/Jap/TBJsLCxx4W/vv/ASb7ikU="
)
