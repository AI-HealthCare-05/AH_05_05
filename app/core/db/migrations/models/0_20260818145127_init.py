from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `hashed_password` VARCHAR(255) NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'PENDING: PENDING\nACTIVE: ACTIVE\nSUSPENDED: SUSPENDED\nWITHDRAWN: WITHDRAWN' DEFAULT 'PENDING',
    `name` VARCHAR(100) NOT NULL,
    `phone` LONGTEXT,
    `is_alarm` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_user_status_ec9fb9` (`status`),
    KEY `idx_user_created_b19d59` (`created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `admin` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `hashed_password` VARCHAR(255) NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'PENDING: PENDING\nACTIVE: ACTIVE\nSUSPENDED: SUSPENDED\nWITHDRAWN: WITHDRAWN' DEFAULT 'PENDING',
    `name` VARCHAR(100) NOT NULL,
    `role` VARCHAR(5) NOT NULL COMMENT 'ADMIN: ADMIN\nSTAFF: STAFF' DEFAULT 'STAFF',
    `approved_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT,
    CONSTRAINT `fk_admin_admin_09b31ccb` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_admin_role_be0fac` (`role`),
    KEY `idx_admin_status_bd769e` (`status`),
    KEY `idx_admin_created_ef2176` (`created_by_admin_id`),
    KEY `idx_admin_created_abe085` (`created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `care_episodes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `title` VARCHAR(150) NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nCOMPLETED: COMPLETED\nCANCELLED: CANCELLED' DEFAULT 'ACTIVE',
    `started_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `default_end_at` DATETIME(6),
    `planned_end_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_care_epi_user_04599d52` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_care_episod_user_id_4f8b7b` (`user_id`, `status`),
    KEY `idx_care_episod_user_id_0c2355` (`user_id`, `planned_end_at`),
    CONSTRAINT `chk_care_episode_default_end` CHECK (`default_end_at` IS NULL OR `default_end_at` >= `started_at`),
    CONSTRAINT `chk_care_episode_planned_end` CHECK (`planned_end_at` IS NULL OR `planned_end_at` >= `started_at`),
    CONSTRAINT `chk_care_episode_completed` CHECK (`completed_at` IS NULL OR `completed_at` >= `started_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `ocr_jobs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `document_type` VARCHAR(21) NOT NULL COMMENT 'DISCHARGE_SUMMARY: DISCHARGE_SUMMARY\nDISCHARGE_INSTRUCTION: DISCHARGE_INSTRUCTION\nPRESCRIPTION: PRESCRIPTION\nMEDICATION_GUIDE: MEDICATION_GUIDE\nMEDICATION_BAG: MEDICATION_BAG',
    `status` VARCHAR(16) NOT NULL COMMENT 'QUEUED: QUEUED\nPROCESSING: PROCESSING\nREADY_FOR_REVIEW: READY_FOR_REVIEW\nCOMPLETE: COMPLETE\nFAILED: FAILED\nCANCELLED: CANCELLED' DEFAULT 'QUEUED',
    `masking_status` VARCHAR(9) NOT NULL COMMENT 'PENDING: PENDING\nCOMPLETED: COMPLETED\nSUSPECTED: SUSPECTED\nFAILED: FAILED' DEFAULT 'PENDING',
    `idempotency_key` VARCHAR(100) NOT NULL UNIQUE,
    `content_hash` VARCHAR(71) NOT NULL,
    `page_count` INT NOT NULL DEFAULT 1,
    `pipeline_version` VARCHAR(50) NOT NULL,
    `error_code` VARCHAR(100),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `completed_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ocr_jobs_care_epi_5d7af6f9` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    KEY `idx_ocr_jobs_care_ep_a1a591` (`care_episode_id`, `status`),
    KEY `idx_ocr_jobs_content_fee3bc` (`content_hash`),
    CONSTRAINT `chk_ocr_jobs_page_count` CHECK (`page_count` >= 1)
) CHARACTER SET utf8mb4;
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
CREATE TABLE IF NOT EXISTS `care_advices` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `text` VARCHAR(500) NOT NULL,
    `display_order` INT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    `source_extracted_field_id` BIGINT,
    UNIQUE KEY `uid_care_advice_care_ep_3d384b` (`care_episode_id`, `display_order`),
    CONSTRAINT `fk_care_adv_care_epi_d3ee7009` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_care_adv_ocr_extr_a9606e6c` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL,
    CONSTRAINT `chk_care_advices_display_order` CHECK (`display_order` >= 1)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `follow_up_visits` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `visit_at` DATETIME(6) NOT NULL,
    `department` VARCHAR(100),
    `doctor_name` VARCHAR(100),
    `place` VARCHAR(255),
    `purpose` VARCHAR(255),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    `source_extracted_field_id` BIGINT,
    CONSTRAINT `fk_follow_u_care_epi_89b64129` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_follow_u_ocr_extr_9689a29b` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL,
    KEY `idx_follow_up_v_care_ep_c495b2` (`care_episode_id`),
    KEY `idx_follow_up_v_visit_a_8be3c7` (`visit_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `recovery_guides` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(10) NOT NULL COMMENT 'COMPLETED: COMPLETED\nSUPERSEDED: SUPERSEDED' DEFAULT 'COMPLETED',
    `guide_content` JSON,
    `patient_context_hash` VARCHAR(64) NOT NULL,
    `model_name` VARCHAR(100),
    `model_version` VARCHAR(100),
    `prompt_version` VARCHAR(100),
    `schema_version` VARCHAR(50),
    `langsmith_trace_id` VARCHAR(100),
    `safety_status` VARCHAR(17) NOT NULL COMMENT 'PENDING: PENDING\nSAFE: SAFE\nRESTRICTED: RESTRICTED\nBLOCKED: BLOCKED\nVALIDATION_FAILED: VALIDATION_FAILED' DEFAULT 'PENDING',
    `safety_reason_code` VARCHAR(100),
    `error_code` VARCHAR(100),
    `completed_at` DATETIME(6),
    `superseded_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    CONSTRAINT `fk_recovery_care_epi_31621b29` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    KEY `idx_recovery_gu_care_ep_74cb03` (`care_episode_id`, `status`),
    KEY `idx_recovery_gu_patient_e9a39c` (`patient_context_hash`),
    KEY `idx_recovery_gu_langsmi_40c0f1` (`langsmith_trace_id`),
    KEY `idx_recovery_gu_created_2b8e18` (`created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `recovery_guide_sources` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_type` VARCHAR(19) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK',
    `public_dataset_key` VARCHAR(100),
    `dataset_version` VARCHAR(100),
    `vector_chunk_id` VARCHAR(255),
    `source_record_key` VARCHAR(100),
    `source_field` VARCHAR(100),
    `chunk_type` VARCHAR(100),
    `source_title` VARCHAR(255),
    `source_organization` VARCHAR(255),
    `source_url` LONGTEXT,
    `similarity_score` DECIMAL(5,4),
    `citation_order` INT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `extracted_field_id` BIGINT,
    `recovery_guide_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_recovery_gu_recover_f0177b` (`recovery_guide_id`, `citation_order`),
    CONSTRAINT `fk_recovery_ocr_extr_7b3aa9bf` FOREIGN KEY (`extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_recovery_recovery_528abdbe` FOREIGN KEY (`recovery_guide_id`) REFERENCES `recovery_guides` (`id`) ON DELETE CASCADE,
    KEY `idx_recovery_gu_recover_6694dc` (`recovery_guide_id`),
    KEY `idx_recovery_gu_extract_f6412c` (`extracted_field_id`),
    KEY `idx_recovery_gu_public__eeffbb` (`public_dataset_key`, `source_record_key`),
    KEY `idx_recovery_gu_vector__2801d1` (`vector_chunk_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_sessions` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(7) NOT NULL COMMENT 'ACTIVE: ACTIVE\nDELETED: DELETED' DEFAULT 'ACTIVE',
    `last_message_at` DATETIME(6),
    `deleted_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    CONSTRAINT `fk_chat_ses_care_epi_836d5018` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_sessio_care_ep_4b8aff` (`care_episode_id`, `status`),
    KEY `idx_chat_sessio_last_me_ee7e71` (`last_message_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_messages` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `request_id` VARCHAR(100),
    `sequence_no` INT NOT NULL,
    `role` VARCHAR(9) NOT NULL COMMENT 'USER: USER\nASSISTANT: ASSISTANT\nSYSTEM: SYSTEM',
    `content` LONGTEXT NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'PENDING: PENDING\nSTREAMING: STREAMING\nCOMPLETED: COMPLETED\nFAILED: FAILED' DEFAULT 'PENDING',
    `route_type` VARCHAR(21) COMMENT 'PATIENT_DB: PATIENT_DB\nPUBLIC_RAG: PUBLIC_RAG\nPATIENT_AND_PUBLIC: PATIENT_AND_PUBLIC\nGENERAL_LIFESTYLE: GENERAL_LIFESTYLE\nSAFETY_RESPONSE: SAFETY_RESPONSE\nOUT_OF_SCOPE_RESPONSE: OUT_OF_SCOPE_RESPONSE',
    `safety_status` VARCHAR(17) NOT NULL COMMENT 'PENDING: PENDING\nSAFE: SAFE\nRESTRICTED: RESTRICTED\nBLOCKED: BLOCKED\nVALIDATION_FAILED: VALIDATION_FAILED' DEFAULT 'PENDING',
    `safety_reason_code` VARCHAR(100),
    `verification_status` VARCHAR(12) NOT NULL COMMENT 'NOT_REQUIRED: NOT_REQUIRED\nPENDING: PENDING\nVERIFIED: VERIFIED\nFAILED: FAILED' DEFAULT 'NOT_REQUIRED',
    `conflict_status` VARCHAR(22) NOT NULL COMMENT 'NOT_APPLICABLE: NOT_APPLICABLE\nNO_CONFLICT: NO_CONFLICT\nPATIENT_DATA_PRIORITY: PATIENT_DATA_PRIORITY\nPUBLIC_SOURCE_EXCLUDED: PUBLIC_SOURCE_EXCLUDED\nREVIEW_REQUIRED: REVIEW_REQUIRED' DEFAULT 'NOT_APPLICABLE',
    `model_name` VARCHAR(100),
    `model_version` VARCHAR(100),
    `prompt_version` VARCHAR(100),
    `schema_version` VARCHAR(50),
    `patient_context_hash` VARCHAR(64),
    `langsmith_trace_id` VARCHAR(100),
    `error_code` VARCHAR(100),
    `started_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `chat_session_id` BIGINT NOT NULL,
    `guide_id` BIGINT,
    `reply_to_message_id` BIGINT,
    UNIQUE KEY `uid_chat_messag_chat_se_d742be` (`chat_session_id`, `sequence_no`),
    CONSTRAINT `fk_chat_mes_chat_ses_01d5d273` FOREIGN KEY (`chat_session_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_mes_recovery_6732baf3` FOREIGN KEY (`guide_id`) REFERENCES `recovery_guides` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_chat_mes_chat_mes_0219f83a` FOREIGN KEY (`reply_to_message_id`) REFERENCES `chat_messages` (`id`) ON DELETE SET NULL,
    KEY `idx_chat_messag_reply_t_884c0e` (`reply_to_message_id`),
    KEY `idx_chat_messag_guide_i_99461b` (`guide_id`),
    KEY `idx_chat_messag_request_17f9b3` (`request_id`),
    KEY `idx_chat_messag_langsmi_2c46fb` (`langsmith_trace_id`),
    KEY `idx_chat_messag_created_d01bf5` (`created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_message_sources` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_type` VARCHAR(19) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK',
    `public_dataset_key` VARCHAR(100),
    `dataset_version` VARCHAR(100),
    `vector_chunk_id` VARCHAR(255),
    `source_record_key` VARCHAR(100),
    `source_field` VARCHAR(100),
    `chunk_type` VARCHAR(100),
    `source_title` VARCHAR(255),
    `source_organization` VARCHAR(255),
    `source_url` LONGTEXT,
    `similarity_score` DECIMAL(5,4),
    `citation_order` INT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `chat_message_id` BIGINT NOT NULL,
    `extracted_field_id` BIGINT,
    UNIQUE KEY `uid_chat_messag_chat_me_2b0b11` (`chat_message_id`, `citation_order`),
    CONSTRAINT `fk_chat_mes_chat_mes_9ab18214` FOREIGN KEY (`chat_message_id`) REFERENCES `chat_messages` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_mes_ocr_extr_ccc3036d` FOREIGN KEY (`extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL,
    KEY `idx_chat_messag_chat_me_b7dff7` (`chat_message_id`),
    KEY `idx_chat_messag_extract_282037` (`extracted_field_id`),
    KEY `idx_chat_messag_public__62f00e` (`public_dataset_key`, `source_record_key`),
    KEY `idx_chat_messag_vector__7b212a` (`vector_chunk_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `alarms` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alarm_type` VARCHAR(15) NOT NULL COMMENT 'MEDICATION: MEDICATION\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT\nCUSTOM: CUSTOM' DEFAULT 'CUSTOM',
    `title` VARCHAR(255) NOT NULL,
    `message` VARCHAR(500),
    `scheduled_at` DATETIME(6) NOT NULL,
    `recurrence_rule` VARCHAR(100),
    `timezone` VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    `next_trigger_at` DATETIME(6) NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nPAUSED: PAUSED\nCOMPLETED: COMPLETED\nCANCELLED: CANCELLED' DEFAULT 'ACTIVE',
    `last_triggered_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `cancelled_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT,
    `source_guide_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_alarms_care_epi_f84e08b5` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_alarms_recovery_35468ea9` FOREIGN KEY (`source_guide_id`) REFERENCES `recovery_guides` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_alarms_user_f2255a38` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_alarms_user_id_7ea094` (`user_id`, `status`),
    KEY `idx_due_alarms` (`status`, `next_trigger_at`),
    KEY `idx_alarms_care_ep_8fee4d` (`care_episode_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `push_subscriptions` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `endpoint` VARCHAR(500) NOT NULL UNIQUE,
    `p256dh_key` VARCHAR(255) NOT NULL,
    `auth_key` VARCHAR(255) NOT NULL,
    `platform` VARCHAR(50),
    `user_agent` VARCHAR(255),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `last_used_at` DATETIME(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_push_sub_user_72210781` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_push_subscr_user_id_a8b49c` (`user_id`, `is_active`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `alarm_events` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `event_type` VARCHAR(9) NOT NULL COMMENT 'SCHEDULED: SCHEDULED\nSENT: SENT\nDELIVERED: DELIVERED\nCOMPLETED: COMPLETED\nSKIPPED: SKIPPED\nFAILED: FAILED',
    `event_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `payload` JSON,
    `error_code` VARCHAR(100),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `alarm_id` BIGINT NOT NULL,
    `push_subscription_id` BIGINT,
    CONSTRAINT `fk_alarm_ev_alarms_1ccaf822` FOREIGN KEY (`alarm_id`) REFERENCES `alarms` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_alarm_ev_push_sub_34da4d41` FOREIGN KEY (`push_subscription_id`) REFERENCES `push_subscriptions` (`id`) ON DELETE SET NULL,
    KEY `idx_alarm_event_alarm_i_c369bb` (`alarm_id`, `event_type`),
    KEY `idx_alarm_event_event_a_9befa3` (`event_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `background_jobs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `job_type` VARCHAR(13) NOT NULL COMMENT 'OCR: OCR\nLLM: LLM\nCHAT: CHAT\nALARM: ALARM\nDATA_DELETION: DATA_DELETION',
    `status` VARCHAR(13) NOT NULL COMMENT 'QUEUED: QUEUED\nPROCESSING: PROCESSING\nRETRY_WAITING: RETRY_WAITING\nCOMPLETED: COMPLETED\nFAILED: FAILED\nCANCELLED: CANCELLED' DEFAULT 'QUEUED',
    `reference_table` VARCHAR(50),
    `reference_id` BIGINT,
    `requested_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `started_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `duration_ms` INT,
    `retry_count` INT NOT NULL DEFAULT 0,
    `max_retry_count` INT NOT NULL DEFAULT 0,
    `error_code` VARCHAR(100),
    `error_message` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `parent_job_id` BIGINT,
    `user_id` BIGINT,
    CONSTRAINT `fk_backgrou_backgrou_c9481008` FOREIGN KEY (`parent_job_id`) REFERENCES `background_jobs` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_backgrou_user_a936cdba` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_background__job_typ_5ee2bd` (`job_type`, `status`),
    KEY `idx_background__request_f3f5f7` (`requested_at`),
    KEY `idx_background__user_id_6d5c58` (`user_id`),
    KEY `idx_queue_stats` (`status`, `requested_at`),
    CONSTRAINT `chk_background_jobs_retry_count` CHECK (`retry_count` >= 0)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `medications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `dose` VARCHAR(100),
    `times_per_day` INT,
    `note` VARCHAR(255),
    `days` INT,
    `prescribed_at` DATE,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    `source_extracted_field_id` BIGINT,
    `source_ocr_job_id` BIGINT,
    CONSTRAINT `fk_medicati_care_epi_e438de8c` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_medicati_ocr_extr_cb0f373d` FOREIGN KEY (`source_extracted_field_id`) REFERENCES `ocr_extracted_fields` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_medicati_ocr_jobs_bef8e991` FOREIGN KEY (`source_ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE SET NULL,
    KEY `idx_medications_care_ep_f02ed7` (`care_episode_id`),
    KEY `idx_medications_care_ep_003a2c` (`care_episode_id`, `name`),
    KEY `idx_medications_care_ep_df8ea7` (`care_episode_id`, `source_ocr_job_id`),
    CONSTRAINT `chk_medications_times_per_day` CHECK (`times_per_day` IS NULL OR `times_per_day` BETWEEN 1 AND 6),
    CONSTRAINT `chk_medications_days` CHECK (`days` IS NULL OR `days` >= 1)
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
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "qN1RrH/xbrXQeEfate4/rx/9iw2l0="
)
