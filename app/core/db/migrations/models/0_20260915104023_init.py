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
    `birth_date` DATE,
    `gender` VARCHAR(6) COMMENT 'MALE: MALE\nFEMALE: FEMALE',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_user_status_ec9fb9` (`status`),
    KEY `idx_user_created_b19d59` (`created_at`)
) CHARACTER SET utf8mb4;
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
CREATE TABLE IF NOT EXISTS `user_settings` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `is_notify_medication` BOOL NOT NULL DEFAULT 0,
    `is_notify_supplement` BOOL NOT NULL DEFAULT 0,
    `is_notify_schedule` BOOL NOT NULL DEFAULT 0,
    `is_notify_guide` BOOL NOT NULL DEFAULT 0,
    `is_terms_agreed` BOOL NOT NULL DEFAULT 0,
    `terms_agreed_at` DATETIME(6),
    `notify_consented_at` DATETIME(6),
    `morning_medication_time` TIME(6) NOT NULL DEFAULT '08:00:00',
    `lunch_medication_time` TIME(6) NOT NULL DEFAULT '13:00:00',
    `evening_medication_time` TIME(6) NOT NULL DEFAULT '19:00:00',
    `bedtime_medication_time` TIME(6) NOT NULL DEFAULT '22:00:00',
    `user_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_user_set_user_67a93e12` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
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
CREATE TABLE IF NOT EXISTS `admin_settings` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '관리자 설정 식별자',
    `setting_key` VARCHAR(50) NOT NULL UNIQUE COMMENT '관리자 설정 구분 키',
    `smtp_host` VARCHAR(255) NOT NULL COMMENT 'SMTP 서버 주소',
    `smtp_port` INT NOT NULL COMMENT 'SMTP 서버 포트',
    `smtp_user` VARCHAR(255) NOT NULL COMMENT 'SMTP 인증 계정',
    `smtp_password_enc` VARCHAR(500) NOT NULL COMMENT '암호화된 SMTP 인증 비밀번호',
    `smtp_from_email` VARCHAR(255) NOT NULL COMMENT 'SMTP 발신 이메일 주소',
    `created_at` DATETIME(6) NOT NULL COMMENT '설정 생성 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL COMMENT '설정 최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `updated_by_admin_id` BIGINT NOT NULL COMMENT '설정을 마지막으로 변경한 관리자 식별자',
    CONSTRAINT `fk_admin_se_admin_ca833aa0` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE RESTRICT,
    KEY `idx_admin_setti_updated_1a1b7d` (`updated_by_admin_id`),
    KEY `idx_admin_setti_updated_533b9f` (`updated_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `care_episodes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alias` VARCHAR(255),
    `hospital_name` VARCHAR(255),
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nCOMPLETED: COMPLETED\nCANCELLED: CANCELLED' DEFAULT 'ACTIVE',
    `medication_days` INT,
    `source_ocr_job_id` BIGINT,
    `confirmation_hash` VARCHAR(64),
    `confirmed_at` DATETIME(6),
    `medication_start_date` DATE,
    `medication_start_slot` VARCHAR(7) COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `completed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_care_epi_user_04599d52` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_care_episod_user_id_4f8b7b` (`user_id`, `status`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `follow_up_visits` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `visit_date` DATE NOT NULL,
    `visit_time` TIME(6),
    `hospital` VARCHAR(255),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_follow_u_user_8f0f463b` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_follow_up_v_user_id_d26d61` (`user_id`),
    KEY `idx_follow_up_v_visit_d_dbbd94` (`visit_date`, `visit_time`, `id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `ocr_jobs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(16) NOT NULL COMMENT 'QUEUED: QUEUED\nPROCESSING: PROCESSING\nREADY_FOR_REVIEW: READY_FOR_REVIEW\nCOMPLETE: COMPLETE\nFAILED: FAILED\nCANCELLED: CANCELLED' DEFAULT 'QUEUED',
    `idempotency_key` VARCHAR(100) NOT NULL,
    `input_manifest` JSON NOT NULL,
    `structured_result` JSON,
    `ocr_model` VARCHAR(100) NOT NULL,
    `structuring_model` VARCHAR(100),
    `prompt_version` VARCHAR(100),
    `schema_version` VARCHAR(50) NOT NULL,
    `stage_results` JSON,
    `avg_field_confidence` DECIMAL(5,4),
    `confidence_field_count` INT,
    `user_review_match_rate` DECIMAL(5,4),
    `error_code` VARCHAR(100),
    `started_at` DATETIME(6),
    `ready_at` DATETIME(6),
    `expires_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `care_episode_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ocr_jobs_user_id_825f43` (`user_id`, `idempotency_key`),
    UNIQUE KEY `uid_ocr_jobs_id_d66b71` (`id`, `care_episode_id`),
    CONSTRAINT `fk_ocr_jobs_care_epi_5d7af6f9` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_ocr_jobs_user_33066343` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_ocr_jobs_care_ep_a1a591` (`care_episode_id`, `status`),
    KEY `idx_ocr_jobs_expires_c6acd3` (`expires_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_sessions` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(7) NOT NULL COMMENT 'ACTIVE: ACTIVE\nDELETED: DELETED' DEFAULT 'ACTIVE',
    `is_like` BOOL COMMENT '좋아요 여부',
    `reason_code` VARCHAR(20) COMMENT '평가 사유 코드',
    `last_message_at` DATETIME(6),
    `deleted_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_chat_ses_care_epi_836d5018` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_ses_user_91ae8bac` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_sessio_user_id_5d846b` (`user_id`, `status`, `last_message_at`),
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
    `route_type` VARCHAR(21) COMMENT 'PATIENT_DB: PATIENT_DB\nPUBLIC_RAG: PUBLIC_RAG\nPATIENT_AND_PUBLIC: PATIENT_AND_PUBLIC\nGENERAL_LIFESTYLE: GENERAL_LIFESTYLE\nINTERACTION: INTERACTION\nSAFETY_RESPONSE: SAFETY_RESPONSE\nOUT_OF_SCOPE_RESPONSE: OUT_OF_SCOPE_RESPONSE',
    `safety_status` VARCHAR(17) NOT NULL COMMENT 'PENDING: PENDING\nSAFE: SAFE\nRESTRICTED: RESTRICTED\nBLOCKED: BLOCKED\nVALIDATION_FAILED: VALIDATION_FAILED' DEFAULT 'PENDING',
    `safety_reason_code` VARCHAR(100),
    `model_name` VARCHAR(100),
    `model_version` VARCHAR(100),
    `prompt_version` VARCHAR(100),
    `schema_version` VARCHAR(50),
    `session_reference` JSON,
    `patient_context_hash` VARCHAR(64),
    `langsmith_trace_id` VARCHAR(100),
    `error_code` VARCHAR(100),
    `duration_ms` INT,
    `started_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `chat_session_id` BIGINT NOT NULL,
    `reply_to_message_id` BIGINT,
    UNIQUE KEY `uid_chat_messag_chat_se_d742be` (`chat_session_id`, `sequence_no`),
    CONSTRAINT `fk_chat_mes_chat_ses_01d5d273` FOREIGN KEY (`chat_session_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_mes_chat_mes_0219f83a` FOREIGN KEY (`reply_to_message_id`) REFERENCES `chat_messages` (`id`) ON DELETE SET NULL,
    KEY `idx_chat_messag_reply_t_884c0e` (`reply_to_message_id`),
    KEY `idx_chat_messag_request_17f9b3` (`request_id`),
    KEY `idx_chat_messag_langsmi_2c46fb` (`langsmith_trace_id`),
    KEY `idx_chat_messag_created_d01bf5` (`created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `common_code_groups` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '공통코드 그룹 식별자',
    `category` VARCHAR(20) NOT NULL COMMENT '공통코드 대분류',
    `group_code` VARCHAR(20) NOT NULL UNIQUE COMMENT '코드그룹',
    `group_name` VARCHAR(20) NOT NULL COMMENT '코드그룹명',
    `description` VARCHAR(200) COMMENT '코드그룹 설명',
    `is_active` BOOL NOT NULL COMMENT '사용 여부' DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL COMMENT '생성 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT COMMENT '생성 관리자 식별자',
    `updated_by_admin_id` BIGINT COMMENT '수정 관리자 식별자',
    CONSTRAINT `fk_common_c_admin_f1188bf0` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_common_c_admin_cf47ede8` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_common_code_categor_f94cf6` (`category`, `is_active`, `group_code`),
    KEY `idx_common_code_created_35b04f` (`created_by_admin_id`),
    KEY `idx_common_code_updated_d2b80c` (`updated_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `common_codes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '공통코드 식별자',
    `detail_code` VARCHAR(20) NOT NULL COMMENT '상세코드',
    `detail_name` VARCHAR(20) NOT NULL COMMENT '상세코드명',
    `description` VARCHAR(200) COMMENT '상세코드 설명',
    `sort_order` INT NOT NULL COMMENT '정렬순서' DEFAULT 0,
    `is_active` BOOL NOT NULL COMMENT '사용 여부' DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL COMMENT '생성 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT COMMENT '생성 관리자 식별자',
    `group_id` BIGINT NOT NULL COMMENT '공통코드 그룹 식별자',
    `updated_by_admin_id` BIGINT COMMENT '수정 관리자 식별자',
    UNIQUE KEY `uid_common_code_group_i_ee484c` (`group_id`, `detail_code`),
    CONSTRAINT `fk_common_c_admin_e71d6c2e` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_common_c_common_c_0aa3a6c0` FOREIGN KEY (`group_id`) REFERENCES `common_code_groups` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_common_c_admin_b8ffa619` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_common_code_group_i_0c91ea` (`group_id`, `is_active`, `sort_order`),
    KEY `idx_common_code_created_2a92b5` (`created_by_admin_id`),
    KEY `idx_common_code_updated_a53424` (`updated_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `badges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '배지 ID',
    `name` VARCHAR(100) NOT NULL UNIQUE COMMENT '배지 이름',
    `description` VARCHAR(500) COMMENT '배지 설명',
    `image_path` VARCHAR(500) NOT NULL COMMENT '배지 이미지 상대 경로',
    `is_active` BOOL NOT NULL COMMENT '배지 사용 여부' DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT COMMENT '등록 관리자 ID',
    `type` BIGINT COMMENT '배지 유형 공통코드 ID(CHL/BDG_TYPE)',
    `updated_by_admin_id` BIGINT COMMENT '최종 수정 관리자 ID',
    CONSTRAINT `fk_badges_admin_7205d3f9` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_badges_common_c_0dc191f8` FOREIGN KEY (`type`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_badges_admin_f1c4c10f` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_badges_active` (`is_active`),
    KEY `idx_badges_type` (`type`),
    KEY `idx_badges_created_admin` (`created_by_admin_id`),
    KEY `idx_badges_updated_admin` (`updated_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `challenges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '챌린지 ID',
    `name` VARCHAR(100) NOT NULL COMMENT '챌린지명',
    `phrase` VARCHAR(255) NOT NULL COMMENT '챌린지 화면에 표시할 짧은 문구',
    `description` LONGTEXT COMMENT '챌린지 상세 설명',
    `recruit_start_at` DATETIME(6) NOT NULL COMMENT '모집 시작 일시',
    `recruit_end_at` DATETIME(6) NOT NULL COMMENT '모집 종료 일시',
    `is_displayed` BOOL NOT NULL COMMENT '사용자 화면 전시 여부' DEFAULT 0,
    `is_deleted` BOOL NOT NULL COMMENT '소프트 삭제 여부' DEFAULT 0,
    `deleted_at` DATETIME(6) COMMENT '삭제 처리 일시',
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `challenge_period_id` BIGINT NOT NULL COMMENT '챌린지 기간 공통코드 ID(CHL/CHL_PERIOD)',
    `challenge_type_id` BIGINT NOT NULL COMMENT '챌린지 유형 공통코드 ID(CHL/CHL_TYPE)',
    `check_frequency_id` BIGINT NOT NULL COMMENT '인증 빈도 공통코드 ID(CHL/CHK_FREQ)',
    `check_type_id` BIGINT NOT NULL COMMENT '인증 방식 공통코드 ID(CHL/CHK_TYPE)',
    `created_by_admin_id` BIGINT COMMENT '등록 관리자 ID',
    `reward_badge_id` BIGINT COMMENT '챌린지 완료 시 지급할 배지 ID',
    `updated_by_admin_id` BIGINT COMMENT '최종 수정 관리자 ID',
    CONSTRAINT `fk_challeng_common_c_0d01ffbb` FOREIGN KEY (`challenge_period_id`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_common_c_97993fe4` FOREIGN KEY (`challenge_type_id`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_common_c_cf3c82c7` FOREIGN KEY (`check_frequency_id`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_common_c_d9f0068b` FOREIGN KEY (`check_type_id`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_admin_4ef905ac` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_challeng_badges_65a78387` FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_admin_7cfd7ee8` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_challenges_display_period` (`is_displayed`, `is_deleted`, `recruit_start_at`, `recruit_end_at`),
    KEY `idx_challenges_type` (`challenge_type_id`, `is_deleted`),
    KEY `idx_challenges_period` (`challenge_period_id`),
    KEY `idx_challenges_check_type` (`check_type_id`),
    KEY `idx_challenges_check_frequency` (`check_frequency_id`),
    KEY `idx_challenges_reward_badge` (`reward_badge_id`),
    KEY `idx_challenges_created_admin` (`created_by_admin_id`),
    KEY `idx_challenges_updated_admin` (`updated_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `custom_challenge_templates` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '맞춤 챌린지 템플릿 ID',
    `name` VARCHAR(100) NOT NULL UNIQUE COMMENT '템플릿명',
    `is_active` BOOL NOT NULL COMMENT '사용 여부' DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `challenge_type` BIGINT COMMENT '맞춤 챌린지 유형 공통코드 ID(CHL/CST_CHL_TYPE)',
    `check_type_id` BIGINT NOT NULL COMMENT '인증 방식 공통코드 ID(CHL/CST_CHK_TYPE)',
    `created_by_admin_id` BIGINT COMMENT '등록 관리자 ID',
    `reward_badge_id` BIGINT COMMENT '맞춤 챌린지 완료 시 지급할 배지 ID',
    `updated_by_admin_id` BIGINT COMMENT '최종 수정 관리자 ID',
    CONSTRAINT `fk_custom_c_common_c_a2b4c147` FOREIGN KEY (`challenge_type`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_common_c_b2863747` FOREIGN KEY (`check_type_id`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_admin_16ad84a9` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_custom_c_badges_d78c0e0f` FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_admin_cd724db0` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_custom_challenge_templates_active_name` (`is_active`, `name`),
    KEY `idx_custom_challenge_templates_check_type` (`check_type_id`),
    KEY `idx_custom_challenge_templates_challenge_type` (`challenge_type`),
    KEY `idx_custom_challenge_templates_reward_badge` (`reward_badge_id`),
    KEY `idx_custom_challenge_templates_created_admin` (`created_by_admin_id`),
    KEY `idx_custom_challenge_templates_updated_admin` (`updated_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_challenges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '사용자 챌린지 참여 ID',
    `status` VARCHAR(9) NOT NULL COMMENT '참여 상태' DEFAULT 'ACTIVE',
    `joined_at` DATETIME(6) NOT NULL COMMENT '참여 신청 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `started_at` DATETIME(6) NOT NULL COMMENT '실제 챌린지 시작 일시',
    `end_at` DATETIME(6) NOT NULL COMMENT '사용자별 챌린지 종료 예정 일시',
    `target_count` INT NOT NULL DEFAULT 0,
    `completed_count` INT NOT NULL DEFAULT 0,
    `progress_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
    `completed_at` DATETIME(6) COMMENT '챌린지 완료 일시',
    `cancelled_at` DATETIME(6) COMMENT '참여 취소 일시',
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `challenge_id` BIGINT NOT NULL COMMENT '공식 챌린지 ID',
    `user_id` BIGINT NOT NULL COMMENT '참여 사용자 ID',
    CONSTRAINT `fk_user_cha_challeng_1f41b58d` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_cha_user_a9810390` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
    KEY `idx_user_challenges_user_status` (`user_id`, `status`, `joined_at`),
    KEY `idx_user_challenges_challenge_status` (`challenge_id`, `status`),
    KEY `idx_user_challenges_end_at` (`end_at`),
    KEY `idx_user_challenges_user_challenge` (`user_id`, `challenge_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `challenge_progress` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '진행률 ID',
    `period_start` DATE NOT NULL COMMENT '진행률 집계 시작일',
    `period_end` DATE NOT NULL COMMENT '진행률 집계 종료일',
    `target_count` INT NOT NULL DEFAULT 0,
    `completed_count` INT NOT NULL DEFAULT 0,
    `progress_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
    `is_completed` BOOL NOT NULL COMMENT '해당 기간 목표 달성 여부' DEFAULT 0,
    `completed_at` DATETIME(6) COMMENT '해당 기간 목표 달성 일시',
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_challenge_id` BIGINT NOT NULL COMMENT '사용자 챌린지 참여 ID',
    UNIQUE KEY `uid_challenge_p_user_ch_d61468` (`user_challenge_id`, `period_start`, `period_end`),
    CONSTRAINT `fk_challeng_user_cha_cae3e7eb` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`) ON DELETE RESTRICT,
    KEY `idx_challenge_progress_completed` (`user_challenge_id`, `is_completed`),
    KEY `idx_challenge_progress_period_end` (`period_end`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `challenge_verifications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '챌린지 인증 ID',
    `verification_date` DATE NOT NULL COMMENT '사용자 기준 인증일',
    `content` VARCHAR(500) COMMENT '사용자 인증 내용',
    `image_path` VARCHAR(500) COMMENT '인증 이미지 상대 경로',
    `status` VARCHAR(8) NOT NULL COMMENT '인증 처리 상태' DEFAULT 'PENDING',
    `rejection_reason` VARCHAR(500) COMMENT '인증 반려 사유',
    `reviewed_at` DATETIME(6) COMMENT '승인 또는 반려 처리 일시',
    `idempotency_key` VARCHAR(64) NOT NULL UNIQUE COMMENT '인증 중복 등록 방지 키',
    `submitted_at` DATETIME(6) NOT NULL COMMENT '인증 제출 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `progress_id` BIGINT NOT NULL COMMENT '인증이 반영될 진행률 ID',
    `reviewed_by_admin_id` BIGINT COMMENT '수동 인증 검토 관리자 ID',
    `user_challenge_id` BIGINT NOT NULL COMMENT '사용자 챌린지 참여 ID',
    UNIQUE KEY `uid_challenge_v_user_ch_bcb96b` (`user_challenge_id`, `verification_date`),
    CONSTRAINT `fk_challeng_challeng_e3ae9988` FOREIGN KEY (`progress_id`) REFERENCES `challenge_progress` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_admin_219da39f` FOREIGN KEY (`reviewed_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_challeng_user_cha_68c6767c` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`) ON DELETE RESTRICT,
    KEY `idx_challenge_verifications_review` (`status`, `submitted_at`),
    KEY `idx_challenge_verifications_progress` (`progress_id`),
    KEY `idx_challenge_verifications_admin` (`reviewed_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_badges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '사용자 배지 지급 ID',
    `status` VARCHAR(7) NOT NULL COMMENT '배지 지급 상태' DEFAULT 'AWARDED',
    `badge_name` VARCHAR(100) NOT NULL COMMENT '지급 당시 배지 이름 스냅샷',
    `badge_image_path` VARCHAR(500) NOT NULL COMMENT '지급 당시 활성 배지 이미지 경로',
    `awarded_at` DATETIME(6) NOT NULL COMMENT '배지 지급 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `revoked_at` DATETIME(6) COMMENT '배지 회수 일시',
    `revoke_reason` VARCHAR(500) COMMENT '배지 회수 사유',
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `badge_id` BIGINT NOT NULL COMMENT '지급 배지 ID',
    `challenge_id` BIGINT NOT NULL COMMENT '배지 지급 기준 챌린지 ID',
    `user_id` BIGINT NOT NULL COMMENT '배지 지급 사용자 ID',
    `user_challenge_id` BIGINT NOT NULL COMMENT '완료한 사용자 챌린지 참여 ID',
    UNIQUE KEY `uid_user_badges_user_ch_414352` (`user_challenge_id`, `badge_id`),
    CONSTRAINT `fk_user_bad_badges_117d2f2f` FOREIGN KEY (`badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_challeng_d482ced1` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_user_ad1a864e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_user_cha_e64688c1` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`) ON DELETE RESTRICT,
    KEY `idx_user_badges_user_status` (`user_id`, `status`, `awarded_at`),
    KEY `idx_user_badges_challenge` (`challenge_id`, `awarded_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `custom_challenge_participations` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `challenge_type` VARCHAR(10) NOT NULL COMMENT 'MEDICATION: MEDICATION\nSUPPLEMENT: SUPPLEMENT\nVISIT: VISIT',
    `challenge_name` VARCHAR(100) NOT NULL,
    `idempotency_key` VARCHAR(64) NOT NULL,
    `joined_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `end_at` DATETIME(6) NOT NULL,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nCOMPLETED: COMPLETED\nCANCELLED: CANCELLED\nEXPIRED: EXPIRED' DEFAULT 'ACTIVE',
    `target_count` INT NOT NULL DEFAULT 0,
    `completed_count` INT NOT NULL DEFAULT 0,
    `progress_rate` DECIMAL(5,2) NOT NULL DEFAULT 0,
    `completed_at` DATETIME(6),
    `finalized_at` DATETIME(6),
    `reward_badge_id` BIGINT COMMENT '참여 당시 맞춤 챌린지 보상 배지 ID',
    `template_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_custom_chal_user_id_bab620` (`user_id`, `idempotency_key`),
    CONSTRAINT `fk_custom_c_badges_1987430c` FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_custom_c_861bf634` FOREIGN KEY (`template_id`) REFERENCES `custom_challenge_templates` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_user_7936627e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_custom_participation_user_status` (`user_id`, `status`, `joined_at`),
    KEY `idx_custom_participation_template` (`template_id`),
    KEY `idx_custom_participation_reward_badge` (`reward_badge_id`),
    KEY `idx_custom_participation_end_at` (`end_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `custom_challenge_badge_awards` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `badge_name` VARCHAR(100) NOT NULL,
    `badge_image_path` VARCHAR(500) NOT NULL,
    `awarded_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `badge_id` BIGINT NOT NULL,
    `participation_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_custom_chal_partici_438f18` (`participation_id`, `badge_id`),
    CONSTRAINT `fk_custom_c_badges_bdd92054` FOREIGN KEY (`badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_custom_c_2d1f9018` FOREIGN KEY (`participation_id`) REFERENCES `custom_challenge_participations` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_custom_c_user_8192a08b` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
    KEY `idx_custom_badge_award_user_awarded` (`user_id`, `awarded_at`),
    KEY `idx_custom_badge_award_badge` (`badge_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `alarms` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alarm_type` VARCHAR(15) NOT NULL COMMENT 'MEDICATION: MEDICATION\nNUTRIENT: NUTRIENT\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT\nGUIDE_CHECK: GUIDE_CHECK' DEFAULT 'MEDICATION',
    `meal_slot` VARCHAR(7) COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
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
    `follow_up_visit_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_alarms_user_id_e74d92` (`user_id`, `alarm_type`, `meal_slot`),
    CONSTRAINT `fk_alarms_care_epi_f84e08b5` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_alarms_follow_u_3334f0dc` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_alarms_user_f2255a38` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_alarms_user_id_7ea094` (`user_id`, `status`),
    KEY `idx_due_alarms` (`status`, `next_trigger_at`),
    KEY `idx_alarms_care_ep_8fee4d` (`care_episode_id`),
    KEY `idx_alarms_follow__338bbe` (`follow_up_visit_id`)
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
    `idempotency_key` VARCHAR(150) NOT NULL UNIQUE,
    `job_type` VARCHAR(13) NOT NULL COMMENT 'OCR: OCR\nLLM: LLM\nCHAT: CHAT\nALARM: ALARM\nEMAIL: EMAIL\nDATA_DELETION: DATA_DELETION',
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
    `encrypted_payload` LONGTEXT,
    `next_attempt_at` DATETIME(6),
    `lease_expires_at` DATETIME(6),
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
    KEY `idx_email_job_retry_due` (`job_type`, `status`, `next_attempt_at`),
    KEY `idx_email_job_lease` (`job_type`, `status`, `lease_expires_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `email_verifications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(255) NOT NULL,
    `purpose` VARCHAR(30) NOT NULL COMMENT 'SIGNUP: SIGNUP',
    `code_digest` VARCHAR(64) NOT NULL,
    `expires_at` DATETIME(6) NOT NULL,
    `attempt_count` INT NOT NULL DEFAULT 0,
    `verified_at` DATETIME(6),
    `consumed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    KEY `idx_email_verification_lookup` (`email`, `purpose`, `created_at`),
    KEY `idx_email_verification_expiry` (`expires_at`),
    KEY `idx_email_verification_state` (`verified_at`, `consumed_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `medications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `strength` VARCHAR(100),
    `dose_quantity` VARCHAR(50),
    `times_per_day` INT,
    `days` INT,
    `prescribed_at` DATE,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    `source_ocr_job_id` BIGINT,
    CONSTRAINT `fk_medicati_care_epi_e438de8c` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_medicati_ocr_jobs_bef8e991` FOREIGN KEY (`source_ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE SET NULL,
    KEY `idx_medications_care_ep_f02ed7` (`care_episode_id`),
    KEY `idx_medications_care_ep_003a2c` (`care_episode_id`, `name`),
    KEY `idx_medications_care_ep_df8ea7` (`care_episode_id`, `source_ocr_job_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `medication_doses` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `dose_date` DATE NOT NULL,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `taken_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `care_episode_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_medication__user_id_faedc3` (`user_id`, `dose_date`, `slot`, `care_episode_id`),
    CONSTRAINT `fk_medicati_care_epi_7efbd786` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_medicati_user_2b519a1e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__user_id_d81abf` (`user_id`, `dose_date`),
    KEY `idx_medication__care_ep_3c1a64` (`care_episode_id`, `dose_date`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `medication_notes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `dosed_at` DATETIME(6) NOT NULL,
    `body` VARCHAR(500) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `care_episode_id` BIGINT NOT NULL,
    `medication_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_medicati_care_epi_f00ac374` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_medicati_medicati_ded2e5f8` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_medicati_user_8e189084` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_medication__user_id_fcb7b0` (`user_id`, `dosed_at`),
    KEY `idx_medication__care_ep_f944e8` (`care_episode_id`)
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
CREATE TABLE IF NOT EXISTS `display_suppl_nutr_rank` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '영양제 랭킹 전시 식별자',
    `title` VARCHAR(100) NOT NULL COMMENT '전시 제목',
    `start_at` DATETIME(6) NOT NULL COMMENT '전시 시작 일시',
    `end_at` DATETIME(6) NOT NULL COMMENT '전시 종료 일시',
    `is_enabled` BOOL NOT NULL COMMENT '관리자 전시 활성화 여부' DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL COMMENT '전시 생성 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '전시 최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT COMMENT '전시를 생성한 관리자 식별자',
    CONSTRAINT `fk_display__admin_3ab51998` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_display_sup_is_enab_61274f` (`is_enabled`, `start_at`, `end_at`),
    KEY `idx_display_sup_created_6ead6e` (`created_by_admin_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `nutrient_standard` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '영양소 섭취기준 ID',
    `grp` VARCHAR(10) NOT NULL COMMENT '대상 구분',
    `age` VARCHAR(20) COMMENT '연령 구간',
    `carb_g_rni` DECIMAL(10,3) COMMENT '탄수화물 권장섭취량(g/일)',
    `carb_g_ai` DECIMAL(10,3) COMMENT '탄수화물 충분섭취량(g/일)',
    `carb_g_ul` DECIMAL(10,3) COMMENT '탄수화물 상한섭취량(g/일)',
    `protein_g_rni` DECIMAL(10,3) COMMENT '단백질 권장섭취량(g/일)',
    `protein_g_ai` DECIMAL(10,3) COMMENT '단백질 충분섭취량(g/일)',
    `protein_g_ul` DECIMAL(10,3) COMMENT '단백질 상한섭취량(g/일)',
    `fat_g_rni` DECIMAL(10,3) COMMENT '지방 권장섭취량(g/일)',
    `fat_g_ai` DECIMAL(10,3) COMMENT '지방 충분섭취량(g/일)',
    `fat_g_ul` DECIMAL(10,3) COMMENT '지방 상한섭취량(g/일)',
    `fiber_g_rni` DECIMAL(10,3) COMMENT '식이섬유 권장섭취량(g/일)',
    `fiber_g_ai` DECIMAL(10,3) COMMENT '식이섬유 충분섭취량(g/일)',
    `fiber_g_ul` DECIMAL(10,3) COMMENT '식이섬유 상한섭취량(g/일)',
    `calcium_mg_rni` DECIMAL(10,3) COMMENT '칼슘 권장섭취량(mg/일)',
    `calcium_mg_ai` DECIMAL(10,3) COMMENT '칼슘 충분섭취량(mg/일)',
    `calcium_mg_ul` DECIMAL(10,3) COMMENT '칼슘 상한섭취량(mg/일)',
    `iron_mg_rni` DECIMAL(10,3) COMMENT '철 권장섭취량(mg/일)',
    `iron_mg_ai` DECIMAL(10,3) COMMENT '철 충분섭취량(mg/일)',
    `iron_mg_ul` DECIMAL(10,3) COMMENT '철 상한섭취량(mg/일)',
    `phosphorus_mg_rni` DECIMAL(10,3) COMMENT '인 권장섭취량(mg/일)',
    `phosphorus_mg_ai` DECIMAL(10,3) COMMENT '인 충분섭취량(mg/일)',
    `phosphorus_mg_ul` DECIMAL(10,3) COMMENT '인 상한섭취량(mg/일)',
    `potassium_mg_rni` DECIMAL(10,3) COMMENT '칼륨 권장섭취량(mg/일)',
    `potassium_mg_ai` DECIMAL(10,3) COMMENT '칼륨 충분섭취량(mg/일)',
    `potassium_mg_ul` DECIMAL(10,3) COMMENT '칼륨 상한섭취량(mg/일)',
    `sodium_mg_rni` DECIMAL(10,3) COMMENT '나트륨 권장섭취량(mg/일)',
    `sodium_mg_ai` DECIMAL(10,3) COMMENT '나트륨 충분섭취량(mg/일)',
    `sodium_mg_ul` DECIMAL(10,3) COMMENT '나트륨 상한섭취량(mg/일)',
    `vitamin_a_ug_rae_rni` DECIMAL(10,3) COMMENT '비타민 A 권장섭취량(μg RAE/일)',
    `vitamin_a_ug_rae_ai` DECIMAL(10,3) COMMENT '비타민 A 충분섭취량(μg RAE/일)',
    `vitamin_a_ug_rae_ul` DECIMAL(10,3) COMMENT '비타민 A 상한섭취량(μg RAE/일)',
    `thiamine_mg_rni` DECIMAL(10,3) COMMENT '티아민 권장섭취량(mg/일)',
    `thiamine_mg_ai` DECIMAL(10,3) COMMENT '티아민 충분섭취량(mg/일)',
    `thiamine_mg_ul` DECIMAL(10,3) COMMENT '티아민 상한섭취량(mg/일)',
    `riboflavin_mg_rni` DECIMAL(10,3) COMMENT '리보플라빈 권장섭취량(mg/일)',
    `riboflavin_mg_ai` DECIMAL(10,3) COMMENT '리보플라빈 충분섭취량(mg/일)',
    `riboflavin_mg_ul` DECIMAL(10,3) COMMENT '리보플라빈 상한섭취량(mg/일)',
    `niacin_mg_rni` DECIMAL(10,3) COMMENT '나이아신 권장섭취량(mg NE/일)',
    `niacin_mg_ai` DECIMAL(10,3) COMMENT '나이아신 충분섭취량(mg NE/일)',
    `niacin_mg_ul` DECIMAL(10,3) COMMENT '나이아신 상한섭취량(mg NE/일)',
    `vitamin_c_mg_rni` DECIMAL(10,3) COMMENT '비타민 C 권장섭취량(mg/일)',
    `vitamin_c_mg_ai` DECIMAL(10,3) COMMENT '비타민 C 충분섭취량(mg/일)',
    `vitamin_c_mg_ul` DECIMAL(10,3) COMMENT '비타민 C 상한섭취량(mg/일)',
    `vitamin_d_ug_rni` DECIMAL(10,3) COMMENT '비타민 D 권장섭취량(μg/일)',
    `vitamin_d_ug_ai` DECIMAL(10,3) COMMENT '비타민 D 충분섭취량(μg/일)',
    `vitamin_d_ug_ul` DECIMAL(10,3) COMMENT '비타민 D 상한섭취량(μg/일)',
    KEY `idx_nutrient_st_grp_016477` (`grp`, `age`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `supplement_nutrients` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `food_code` VARCHAR(20) NOT NULL UNIQUE,
    `name` VARCHAR(100) NOT NULL,
    `basis_qty` VARCHAR(10) NOT NULL,
    `energy_kcal` INT NOT NULL,
    `water_g` DECIMAL(10,3),
    `protein_g` DECIMAL(5,2) NOT NULL,
    `fat_g` DECIMAL(5,2),
    `ash_g` DECIMAL(10,3),
    `carb_g` DECIMAL(6,2) NOT NULL,
    `sugar_g` DECIMAL(5,2),
    `fiber_g` DECIMAL(7,1),
    `calcium_mg` INT,
    `iron_mg` DECIMAL(5,2),
    `phosphorus_mg` INT,
    `potassium_mg` INT,
    `sodium_mg` INT,
    `vitamin_a_ug_rae` INT,
    `retinol_ug` INT,
    `beta_carotene_ug` INT,
    `thiamine_mg` DECIMAL(6,3),
    `riboflavin_mg` DECIMAL(6,3),
    `niacin_mg` DECIMAL(6,3),
    `vitamin_c_mg` DECIMAL(7,2),
    `vitamin_d_ug` DECIMAL(7,2),
    `cholesterol_mg` DECIMAL(6,2),
    `sat_fat_g` DECIMAL(4,2),
    `trans_fat_g` DECIMAL(4,2),
    `serving_desc` VARCHAR(10) NOT NULL,
    `serving_size` VARCHAR(10) NOT NULL,
    `daily_freq` VARCHAR(5) NOT NULL,
    `target` VARCHAR(10)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `suppl_nutr_rank_item` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '영양제 랭킹 전시 상품 식별자',
    `rank_no` INT NOT NULL COMMENT '전시 순위. 1부터 5까지 사용',
    `created_at` DATETIME(6) NOT NULL COMMENT '전시 상품 생성 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `display_id` BIGINT NOT NULL COMMENT '영양제 랭킹 전시 식별자',
    `supplement_nutrient_id` BIGINT NOT NULL COMMENT '전시할 건강기능식품 식별자',
    UNIQUE KEY `uid_suppl_nutr__display_f8d99a` (`display_id`, `supplement_nutrient_id`),
    UNIQUE KEY `uid_suppl_nutr__display_4fe3eb` (`display_id`, `rank_no`),
    CONSTRAINT `fk_suppl_nu_display__e8c0c99b` FOREIGN KEY (`display_id`) REFERENCES `display_suppl_nutr_rank` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_suppl_nu_suppleme_089e2602` FOREIGN KEY (`supplement_nutrient_id`) REFERENCES `supplement_nutrients` (`id`) ON DELETE RESTRICT
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_suppl_nutrient` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `custom_name` VARCHAR(255),
    `dose_amount` DECIMAL(8,3) NOT NULL,
    `dose_unit` VARCHAR(20) NOT NULL,
    `start_date` DATE NOT NULL,
    `end_date` DATE,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nPAUSED: PAUSED\nCOMPLETED: COMPLETED' DEFAULT 'ACTIVE',
    `note` VARCHAR(500),
    `review_body` VARCHAR(500) COMMENT '다른 사용자에게 공개되는 후기 본문',
    `score` INT COMMENT '사용자가 남긴 별점 1~5',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `supplement_nutrient_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_user_suppl__user_id_4a5cc9` (`user_id`, `supplement_nutrient_id`),
    CONSTRAINT `fk_user_sup_suppleme_45c5bd61` FOREIGN KEY (`supplement_nutrient_id`) REFERENCES `supplement_nutrients` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_sup_user_1edd5404` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_user_suppl__user_id_960087` (`user_id`, `status`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `custom_challenge_targets` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_id_snapshot` BIGINT NOT NULL,
    `target_name_snapshot` LONGTEXT NOT NULL,
    `care_episode_id` BIGINT,
    `follow_up_visit_id` BIGINT,
    `participation_id` BIGINT NOT NULL,
    `supplement_registration_id` BIGINT,
    UNIQUE KEY `uid_custom_chal_partici_4858eb` (`participation_id`, `source_id_snapshot`),
    CONSTRAINT `fk_custom_c_care_epi_ed9d9d79` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_custom_c_follow_u_5aa7b3b0` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_custom_c_custom_c_2e52ef2c` FOREIGN KEY (`participation_id`) REFERENCES `custom_challenge_participations` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_custom_c_user_sup_a26eccd2` FOREIGN KEY (`supplement_registration_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE SET NULL,
    KEY `idx_custom_target_care_episode` (`care_episode_id`),
    KEY `idx_custom_target_supplement_registration` (`supplement_registration_id`),
    KEY `idx_custom_target_follow_up_visit` (`follow_up_visit_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `custom_challenge_occurrences` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `scheduled_date` DATE NOT NULL,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `scheduled_at` DATETIME(6) NOT NULL,
    `is_completed` BOOL NOT NULL DEFAULT 0,
    `target_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_custom_chal_target__f65198` (`target_id`, `scheduled_date`, `slot`),
    CONSTRAINT `fk_custom_c_custom_c_939257b6` FOREIGN KEY (`target_id`) REFERENCES `custom_challenge_targets` (`id`) ON DELETE CASCADE,
    KEY `idx_custom_occurrence_schedule` (`target_id`, `scheduled_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `supplement_doses` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `dose_date` DATE NOT NULL,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `taken_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `registration_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_supplement__registr_f2b8a7` (`registration_id`, `dose_date`, `slot`),
    CONSTRAINT `fk_suppleme_user_sup_5344b871` FOREIGN KEY (`registration_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='One taken dose per registered supplement, calendar day and meal slot.';
CREATE TABLE IF NOT EXISTS `supplement_review_report` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `registration_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_supplement__user_id_9738da` (`user_id`, `registration_id`),
    CONSTRAINT `fk_suppleme_user_sup_05b36c10` FOREIGN KEY (`registration_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_suppleme_user_df475b63` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_supplement__registr_e0df51` (`registration_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_suppl_nutrient_slots` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_suppl_nutrient_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_user_suppl__user_su_d927f2` (`user_suppl_nutrient_id`, `slot`),
    CONSTRAINT `fk_user_sup_user_sup_8183ddbf` FOREIGN KEY (`user_suppl_nutrient_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
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
CREATE TABLE IF NOT EXISTS `medication_product_guides` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `item_seq` VARCHAR(20) NOT NULL UNIQUE,
    `product_name` VARCHAR(255) NOT NULL,
    `manufacturer_name` VARCHAR(255) NOT NULL,
    `efficacy` LONGTEXT NOT NULL,
    `usage_instructions` LONGTEXT NOT NULL,
    `pre_use_warning` LONGTEXT NOT NULL,
    `precautions` LONGTEXT NOT NULL,
    `drug_food_interactions` LONGTEXT NOT NULL,
    `adverse_reactions` LONGTEXT NOT NULL,
    `storage_instructions` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_medication__product_b699d6` (`product_name`)
) CHARACTER SET utf8mb4;
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
    KEY `idx_medication__interac_4bdad9` (`interaction_entity_id`, `rule_type`, `review_status`),
    KEY `idx_medication__rule_da_2e2c4a` (`rule_dataset_version`, `review_status`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_message_sources` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_type` VARCHAR(22) NOT NULL COMMENT 'PATIENT_SAVED_FIELD: PATIENT_SAVED_FIELD\nPUBLIC_RAG_CHUNK: PUBLIC_RAG_CHUNK\nUSER_SUPPLEMENT: USER_SUPPLEMENT\nINTERACTION_RULE: INTERACTION_RULE\nMEDICATION_SAFETY_RULE: MEDICATION_SAFETY_RULE',
    `patient_source_kind` VARCHAR(18) COMMENT 'CARE_EPISODE_FIELD: CARE_EPISODE_FIELD\nMEDICATION: MEDICATION\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT',
    `patient_field` VARCHAR(15) COMMENT 'MEDICATION_DAYS: MEDICATION_DAYS',
    `public_dataset_key` VARCHAR(100),
    `dataset_version` VARCHAR(100),
    `vector_chunk_id` VARCHAR(255),
    `source_record_key` VARCHAR(100),
    `source_field` VARCHAR(100),
    `chunk_type` VARCHAR(100),
    `source_title` VARCHAR(255),
    `source_organization` VARCHAR(255),
    `source_url` LONGTEXT,
    `source_page_number` INT,
    `source_license` VARCHAR(255),
    `similarity_score` DECIMAL(5,4),
    `citation_order` INT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `care_episode_id` BIGINT,
    `chat_message_id` BIGINT NOT NULL,
    `follow_up_visit_id` BIGINT,
    `interaction_rule_id` BIGINT,
    `medication_id` BIGINT,
    `medication_safety_rule_id` BIGINT,
    `user_suppl_nutrient_id` BIGINT,
    UNIQUE KEY `uid_chat_messag_chat_me_2b0b11` (`chat_message_id`, `citation_order`),
    CONSTRAINT `fk_chat_mes_care_epi_e6e04ad2` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_chat_mes_chat_mes_9ab18214` FOREIGN KEY (`chat_message_id`) REFERENCES `chat_messages` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_mes_follow_u_53b251cd` FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_chat_mes_interact_65e4a78b` FOREIGN KEY (`interaction_rule_id`) REFERENCES `interaction_rules` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_chat_mes_medicati_89e5d700` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_chat_mes_medicati_99016ea2` FOREIGN KEY (`medication_safety_rule_id`) REFERENCES `medication_safety_rules` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_chat_mes_user_sup_4624a86e` FOREIGN KEY (`user_suppl_nutrient_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE RESTRICT,
    KEY `idx_chat_messag_chat_me_b7dff7` (`chat_message_id`),
    KEY `idx_chat_messag_care_ep_a7d8ed` (`care_episode_id`),
    KEY `idx_chat_messag_medicat_f9e61f` (`medication_id`),
    KEY `idx_chat_messag_follow__c69f37` (`follow_up_visit_id`),
    KEY `idx_chat_messag_user_su_360dbe` (`user_suppl_nutrient_id`),
    KEY `idx_chat_messag_interac_8c6fd1` (`interaction_rule_id`),
    KEY `idx_chat_messag_medicat_5900ca` (`medication_safety_rule_id`),
    KEY `idx_chat_messag_public__62f00e` (`public_dataset_key`, `source_record_key`),
    KEY `idx_chat_messag_vector__7b212a` (`vector_chunk_id`)
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
    KEY `idx_supplement__interac_3b410c` (`interaction_entity_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `therapeutic_classes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(100) NOT NULL UNIQUE,
    `display_name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_therapeutic_display_ec8588` (`display_name`)
) CHARACTER SET utf8mb4 COMMENT='검수 가능한 약물 치료군의 안정적인 기준 용어.';
CREATE TABLE IF NOT EXISTS `interaction_entity_therapeutic_classes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `review_status` VARCHAR(8) NOT NULL COMMENT 'PENDING: PENDING\nAPPROVED: APPROVED\nREJECTED: REJECTED' DEFAULT 'PENDING',
    `classification_dataset_version` VARCHAR(100) NOT NULL,
    `source_id` VARCHAR(100) NOT NULL,
    `document_id` VARCHAR(150) NOT NULL,
    `record_id` VARCHAR(150) NOT NULL,
    `raw_classification_text` LONGTEXT NOT NULL,
    `source_url` LONGTEXT,
    `approved_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6),
    `interaction_entity_id` BIGINT NOT NULL,
    `therapeutic_class_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_interaction_interac_1b7b00` (`interaction_entity_id`, `therapeutic_class_id`, `classification_dataset_version`),
    CONSTRAINT `fk_interact_interact_40ef8b7e` FOREIGN KEY (`interaction_entity_id`) REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_interact_therapeu_15749aa2` FOREIGN KEY (`therapeutic_class_id`) REFERENCES `therapeutic_classes` (`id`) ON DELETE RESTRICT,
    KEY `idx_interaction_therape_e0427d` (`therapeutic_class_id`, `review_status`),
    KEY `idx_interaction_classif_dc7564` (`classification_dataset_version`)
) CHARACTER SET utf8mb4 COMMENT='상호작용 엔터티와 치료군을 출처·검수 상태와 함께 연결한다.';
CREATE TABLE IF NOT EXISTS `therapeutic_class_aliases` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alias` VARCHAR(255) NOT NULL,
    `normalized_alias` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `therapeutic_class_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_therapeutic_therape_7b1c36` (`therapeutic_class_id`, `normalized_alias`),
    CONSTRAINT `fk_therapeu_therapeu_69e39cc6` FOREIGN KEY (`therapeutic_class_id`) REFERENCES `therapeutic_classes` (`id`) ON DELETE CASCADE,
    KEY `idx_therapeutic_normali_9105f4` (`normalized_alias`)
) CHARACTER SET utf8mb4 COMMENT='사용자 질문에서 치료군을 식별하는 검수된 표현.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztfW1z4kbW9l+h+JSt8pMFDDb4GwPMhA0GL+BJcoeUSkiyrR2QWCEm8d61929/uluvLb"
    "VEt5BQS+6qZAySTgPX6Zfzfv63uTdVbXf8cahZuvLWfGj8b9OQ9xp4Eblz02jKh0NwHV6w"
    "5e0OPSoHz2yPtiUrNrj6Iu+OGrikakfF0g+2bhrgqnHa7eBFUwEP6sZrcOlk6P8+aZJtvm"
    "r2m2aBG7//AS7rhqr9pR29t4dv0ouu7VTsq+oq/Gx0XbLfD+ja1LA/owfhp20lxdyd9kbw"
    "8OHdfjMN/2ndsOHVV83QLNnW4PC2dYJfH34793d6v8j5psEjzlcM0ajai3za2aGfS4mBYh"
    "oQP/BtjugHvsJP+X+ddve+27+96/bBI+ib+Ffu/+v8vOC3O4QIgfm6+V90X7Zl5wkEY4Db"
    "d806wq8UA2/0Jltk9EIkEQjBF49C6AGWhqF3IQAxmDg5obiX/5J2mvFqwwne6fVSMPs6XI"
    "5+Gi5/AE/9Df4aE0xmZ47P3Vsd5x4ENgASLg0GEN3Hqwlgu9WiABA8lQgguocDCD7R1pw1"
    "iIP4j9ViTgYxRBIB8tkAP/B3VVfsm8ZOP9p/8AlrCorwV8MvvT8e/70Lg/fD4/DXKK6j2e"
    "ITQsE82q8WGgUN8AlgDLfMl2+hxQ8vbGXl25+ypUqxO2bHTHo2fmvf2UevyIb8irCCvxj+"
    "PvcQeT6iDT12uKDrqUfLyXuiyIPld7D2ZPt0bILrvzcVS4PzRJLt5h9MR84n/bVGp86g07"
    "m9ve+0bu/6ve79fa/f8o+f+K20c+jT9As8irBJe/5s0vayvmPZVH2CfLbVwlEu/lR6k49v"
    "YB4f5OPxT9MiTNhkMAmk1TytCgHW3S2IeE6M0x5hOgXfSjYULYZtQH09SJtPk/l4Ov/SjO"
    "Hq3XlouC82xnC0nn6dPDScvxtj9byC9ybjh4b/cmP8Ml3/NF4Of5k/NPyXzQwcGlDwZ5DI"
    "nUGUN+gvw0z3nq/m9C5EGDsAIAgYrrW/Eg43nyATiO7GyofktZ78uk6XvPbv7p3ZYv7Fez"
    "wqjuGAbnXLfpPAUUdAdQyuklHFqSLQwsu2vtd+9O5XCeTxcD2JQAS+vupIelm21IC63BnY"
    "fBzOwMYJ/90YnyfOO+dvlq3xjmJt3yWu7LuYkhUItsRpCOdTgq6FUaZNRfiC040T/AZ1Ye"
    "zeXYanbQLTx8lqPXx8wnYCOGvhnQ62C3hXY4zwB0HHYwO+bfzPYj6Jqmr+c+v/acLvJJ9s"
    "UzLMPyVZDYmd3lUPGIyxp4OakbE4ZQ6Mvf4+Uxu+oi/PoLCHZB7T1l/epTf9aJuWrhEk00"
    "/uCJ9/Xmo72SZb8EJK+RyN+BMa8J3P9fxfby57VwP+h7Y82dIk7aAfwU+7EJYRGGrijFRh"
    "QF7M3Q7MwdNB+q4fdftCTD6j0Z4PX+FYFUbFVCzpX+b2QjQWivUPc1thGJQ32ZaO2hFa+C"
    "9dLWColTNShQGR4c8Fx+NWVl/z2FY/wXGuikdzc9oqt63NSRkorYbzZ3OStdYAvmnJCvj3"
    "Th6Af+8HrcZ0TCem0s6mHRRlNekgW7au6AeEUA4wjryRrw2lotz2wb89TSkevRM4e/dSAC"
    "KagxKakZeuTTS0DyKalENIXOGVGoMrzzkXAewpPHSFMZN3srW/EJohHKPCGBxOxzfpeNr6"
    "n3AhHk9gvFVouApDA7WOV8s8GWoOstEnfzA6Eak0e1U6JntN1RX0UyXVPF4qEjz6o43BYB"
    "WeKiFYgC6aHyxADa0yLMfT4bDT9pphS5b2Xdf+BH8OpnWp1rXyh12iUZdo0HrgZJzAeJpx"
    "KURQSgxgmruDVgwipoiMEJqabYPPS0FwYWhrE/xDiWNovOrs2hkiVHCjV0K4Sswylh67Ip"
    "FscwUHs3gxM+5EkL5p6IuG41pEnAsvcS4RJmUKKMCHKNmT3ZyupPliPf38m/Q4GU9Hw/V0"
    "MX9okK5ujODqavTTZPwM/WXxa+HnvjxPx9hD6EIW71qHxnXeSfacd2KOcwOc8N/l3Yng5v"
    "1kmjtNNhJiEMJ0EfZtASHX5xZxKSwWM8zH8mkadZM/P36aLH9oI3TBQ7qNrRfhtKyZc4vg"
    "tISnI+vxEiI6f8ZwwsKrHTMx3yEOdhzpz6al6a/Gz9p77IBJFgf5RDlJDgSXLflPX7AJTy"
    "Cow2s7zdl4RsPVaAjOkf+WFyDty9kJkmdYDj8jdIZVAH5ScoTcmKPcqB891SIwvjCKHUlD"
    "XFECYZ2RpYggAU6BoSIz1PgQAupEqJU3TT3tWEVp8gAC5iSYX0+6mh1jn1oAHAPY1qz9UZ"
    "KBxKyRzsIzAEepBcA4wGF8MuiGBPJKBj9WRB/0fnaqQujuKfAXgtMxE1sThhCsLZm1e9My"
    "oIUy5Cf0cI/kmCSyNmWIJPYWadZptvoPrRb4r1kYhzE2ElkY2CL7fyOxDXIM48PuZChvl3"
    "AhcYBSeNC+rSAPtO/apWshZYhy+DCoIB+2mgpBuYQPKUOUwodOp4J84MMOXB+j0UUlH85Z"
    "jL3IgYLtxUVzoxhr8UUW4KG6140mqQATunGTWn/Jf6TYwAIL6KxO7ACpXsb2XXK+iIgu4M"
    "ZKLKpoiCoavAIrqmiIKhp8TO9CqmigwzLj5PZorzi1V+vh58+EiT0cP07B5ER/wCSGT4EJ"
    "7D/MiDTNNpK8iZDq7lnm90ymwgipMBGWbCIUcV51jfMSxSlqwNd4wmVE62M24SQMkMmcUw"
    "JjeYjqi2neMQYwR/j51gbuEKe12STMK8x+s5qsG/Pn2Swt3I9wNMHhLs2XrRy+xM38fI4R"
    "NRhuWONVz2WYyt/udMG//XYPZu93u43NaTtQ+l6FBPAapfXfKuB1vwfz/bcKKp2gbNXNSe"
    "2hS7LaQs+iQgCwBAD401FV9GzXuUQnJdPluHszO4dqFLSVKPIrjQZA6b60EZoqCbpcqyd4"
    "87SqUClqD+LS7/fQlGr3nalaOG7eFPPrKFxeBoa6UkfFp1rVIStryjmZ0WEApe+apb+4Ht"
    "W80PwaGvPayCIwt7cqqrlzf48OmQGamUofIKu25db1Vna0UIqt7Q8AxYunLV4jZe2O+gHW"
    "fa0BLf0gMvd7gI2SQ/0+NNKIrnxfrhC2oESotG/bV5cY/TlaAxRT595V5O4QihKsZXPIDc"
    "svcLQPPS3rAGh5MzRcaEY2vkmqfgSHxfuFcI6dUeJ1VJbgM64Nbr/VRRBCfXxw79Tf8ybw"
    "FfXxIpNAMXNIUiRQyFxyJiDoelmgvwf6NhYDFDLg1ykGqEmeaL5BKfOs4yNm6GxFEjJfCq"
    "lCUhyHZPUObiVqH1r+1JbczeTOpokb6CWHDfRiUQPHvX2Q3swjwVmWAn2YqOzyL6vH9RMC"
    "uw3xVRC+Sv8FsqHdV7KgXEz0EcTMq5uGA5249WA0JdefIOKs3mrgjdrZ9pk2nAsbTEZAJU"
    "cOn5m9HhEvsxe30ijuvsHZ7HXjCiXNUJgBjxKXDTwsq9wDMKt3sMSyegdfb7ttpUHiyFbr"
    "wtsK2uKVft8hy7aD023haXs4eRN/scy9xBx/SyAtmzMuA7YK3GiUjtZyuAEZIPeQfOOI4/"
    "zt8bWMKWpGRc2wHg954ahJlEyoS3wK13FHBTI/0Tz7YWdCsi84a6RSwgBlC4C8xTBwERIV"
    "M0TEOF1YSFSNWUudL0deKVjs1RIs5+V0tC6r1Fq4jxPByBZp85RsY4u1lrpWVV839a5GBj"
    "UOoy5vUgxk8k6XE/KWEnINPIKK9Ee9RladeTzotryTWDONYoQC0won1DnJcc34CRjNnhst"
    "Hp9mkzXMnvNfgqvD+Wgym6Gr3sss2mfO2XPhLiFEL1ziXkygrFZAfH6mRPNkKZrkduZjlt"
    "mJ5NWC8iqnXMhYYhovurV3Jh/MXGbZlYnEldyZ77oUe8FdN7nrcjdmhXKwyWaHitBWMgmq"
    "IqYEqjTF0AYNDkzLZu7qnjhAzRu8x373cWcmODnPyyqJg5Xd/n2xnKMqAO6LjTF7no9+em"
    "igPxtj8nXi3HdfbIxPkzGclg8N90UW6SVt7/d2rPvEDes+vl/tD1BZz7Zf4bRivxJp1SKt"
    "uubuDbFCL1mhfNS/q5NWk+YeEH1QLu6DEqDpatcXhhkvFKvSPWGVN9mW9trxKL9qkmN3uD"
    "xpzX50Blyh8SoOzhH8llxS+eyVM1KF8Yhli8nWq3Zpu9Norhgas7ogXbMxOacQBBpubs2U"
    "q3VgJRrURdtt0Xb7unk5n83dzvzz+fBVP+p2kxAzgD9wkxY18IIelU4H6Tt8+GqBAygfB3"
    "2kb3B03nk6HpAFRUhBaSEFOGdobck41YUG5PJWM6UFGZ+vOEbJNfpxqgvL8nNn6cDMGfnU"
    "4/cCLLIEZZRvgucpHkPYXoXtVdhehe2Vg7UobK91s70Kq6Owsl0G0ge1shVpKXBdGQQTQe"
    "DkSLYNhN0p+doEguwBXdX2B9PWDOUdVWpAdgFnLwonNDi2AMyMgN2+aWAtgLS/Djo4lutW"
    "6IPD8/UmxYhQwfjvfz5Pnt2QbTySyrnx0HD+boyn5WI0Wa2cFiv+642xnAzHv0mfF0tpOf"
    "k6nfzy0IheCWLHg9DxjfF5OEVh487f/CLJ23cUemQ7WUmHtyKtpCMrlsjepBUUIxUNWgJg"
    "jcMJiFCyob9opHor/1gt5gm4xigjsD4b4Of+ruqKfdPY6Uf7Dz5BTsEU/nhMi/Og/OFx+G"
    "sU5dFs8SmqnsEBPsUSVKyTYp8soACDp+AvYACdSJwD7lxp0IXADuUKJG6w7B0Ykdg1YnMY"
    "9d9lBZVIXEmDaSHYHixzf7Bh+WcvyIMW2DilQNWfscqbtpezoBqnrOZGUECZNhuaXZxziC"
    "Bxp51iEUJxglGcYPL3V/fDUEKUqrkKTMT0rin6Xt4l5GAnDBG1wTtj/OiOVTX0x5PR9HE4"
    "+6F342SoAR7ojnHR40I3NpcDPHyATgZLWbzkAaqVcJlb7ioy8Dp9DYCWYCtvkkX27KdN2O"
    "RBxJTVLMu0UN1oluMMpxICQugws7K5M3FK4c4s2Z0JPe7vGdgYphNMLJmJIVs6IxtxSsFI"
    "kXopwn9E+I9YockrVGS614iZIf80ezPiOHG1dNcrFwsSgXN5oysC53IInEvaD3JAL1IXlL"
    "t9gBZDwk53QWvsctIU+UG30GiyUEBmk1SpNnT7JrVSbShUtJDgsnCSNzLhaeAZaA42TEIg"
    "maUddu9gBO8rOSFkFqQ52nBKovc72Xg97nX7TYJfVfOvh3QjEWpWWqhZiFsxoJMNsDiVMM"
    "AGHbeC9RKDM7nEJU5VMZEqN2eLZe4SvADnYx492rJbrDyvJsuHBvx3YwxXqynQhebrh4b/"
    "cmOsflutJ48PDedvM8PMzbnGLfgsWyO5CdfaX8l+Qo+kKnEEaQry5Nd1uqPb149ni/kX7/"
    "Go97vyJZyfJvPxdP6lGZ/V7p2HhvsCzOL1cjJ8RNf8l0m1nfEIXQ5mvGWebM2BNPN2Ex6h"
    "5FqVT8P1dDJfS+NPgEH+643x9PxpNh1JyyFknP8aXHefGc7HknM9oAuubYwvk/lkOZxJs+"
    "nnyWr922zy0Ihd2hhgHweXRuvpYv7QCL0Bc2T4ebL+TVpOVk+L+QpQRy5sjMXzWlp8llaj"
    "xdMk9BzxcpZ502nT5AK3k1OB27EDXn7R7HfpwtUdHYTXRQ745XANhuc7zT7gQg5eb4xPs8"
    "XoZ3jRfbExvg5n0/EQTgHJW/mxS1mY2aapjtpOLo/ajtVHdfkA9JCj27yaRQYmUwtZGFNu"
    "mbtC4FQCTRzNDKGfMUKBqYhSrnWUctmoFhCk7FjkwFnzolnkkNmUQGUSsQhWvjkfrHyQbR"
    "2ouRJSd/+ymXtpJNFXclbn306DYBhmAJdMXUloC9mGRWRtnmiqJ8spz0iqs5Bo2I1QVSsQ"
    "Ib8GUCIquSaBOSLKqkbMFEGtIqhVBLXyvEJDwRjscZBx4or5la8cCBkNZmFGPGGAagl95c"
    "ZHRsOPLo30Y+ozwXG4JGExnw+bjEVn5QNoKFCNu0lMi2fCUr0gfBKOqOdYt7FS8OLaXlkV"
    "LDlav9cKJnWxSQ8pDQCkCywN1yAtJL40tB8puu0YSExLhb0NYiGmGIETNooVN4RXgtBl53"
    "2kM4NzEUWcH0+Hw04yTuCrwvAldANwTYM/EZnIT7vYmJLn5/XvHU7bna7Aav3yUbO9emxu"
    "n2pLU8BvCSoyftcUG1rU3k7GN0m0Zii1qqLDoUvifiJDlB1t6EXtrIZfJ2Pp83QyGwehPK"
    "GL4VggafTT8/zncESQc2VjwKhFafX89DSbPE5g1GLkAhbrIy2fYUBQ9MrGeJyMpyMn1sOL"
    "90FPkq9nCQTpdGiiejrJUT2dmCPYddS47P0GOJF1hiQMVXKI2Gi4nEiTp+lqMZ548yR+Lc"
    "y8MMM2xufFbLb4RXp+kr5OV1MwNSIXsrCx3acx0/eTrfT9JDa+ePvlJQz0Bym7E3WwbsbD"
    "31bYQoIXMkFP0yOjndwiox3rkEE+E6kdpURq4X3yvU8uMBliKgikAle/EVFEOGPAlUBaSV"
    "wL6ZcTl4UZkCUSVxLbYsKrHHhSzrhUWDk51nhC1FnDyWpBkoE9TCXQjGpZup2UzZU6P326"
    "SiJa5G5qWq+yof/Ht5wxAhslF/hG8D1ZhArQyTlwOFVF0Lx6FpwD0gGaFYHmtSWVv0hOiy"
    "USV8ufll8QlQMGUJM045hlYw1RVmSyXmPp63t9J1s6zMYC4iZrZVcSuajpGjHq0y/4OGHF"
    "QhZyW+0iOKumwVmittkVQ3owr2amAKocQnk+TABVxO3KDDiZXkzwFMijvmtmzBMGEKCngB"
    "4KDWCFO0YqgKYDOhSDcQno8WEEA87VBsVjZrKVCiWOIaBnDIwtK46To8C6G1JgbEoQp6gn"
    "ml89Ua/qSzNhk84ByorWDo0iGTvmKXCMBi1eDuZnNOLz4as3XmXxJGsGFKCSgj4vBxaWX1"
    "7BQbU9GHAeGriyCCef0hQoxyJoL4d4Ggy5dEesLLYJOhbT3ooFIee5z67QuJXHOFXGT0A6"
    "Oa2j6Oh9LycpIW4/lLJ0JmLfTQkqIFQ/Fojvla4Pitbt5GMge8k2ITo/ePwPpxB0hECEwp"
    "cWCl+96qQwyPyrEy+OB8g6Nx4azt+NMZ64JUjdF006vmDORppSg8mVBmOFBvWjtNO/EXbu"
    "T6a502QjYVYHVBGct4Dsmvt1c3NS+v0t+LfX7YJ/7wbdBnyjKZvTVu236CBOm8WLxQzz4H"
    "yaRqMLnh8/TZY/tCNeSFIeb6ZqjlyVcQR4q7fKYHOSlVYLIt2SAdIK2BTgm5ce4MG2qypZ"
    "ZnaHJuSrkxzx1Ym5e6Pbegz0dIclgVxUHii58oAjLmVxP+OUgpFll5AQcQT1jCMQRV745y"
    "PdChUBIaLZXXXRTfFZiWZ3YeOqcE4V6pzysaQp1hLuoBbZBwqr1sLR/Cy0OsknWSU3uXNu"
    "3KTZNLfwkeKNmf/bDH4LNLJA2/x3VNsDNl63PJuqSxjYJP+SnC/oEcCv7k6JJqIFXxm9QQ"
    "s69BnoKfrhvZwyusE9QX37DsSOvW64/fUoP8sX8yEp/Yd6QmS2D/VF0DMfWiP7cHNz2iq3"
    "rc1JGSitxpTWKMmFsZi1hcdFzTuKARwaz+6h1WzQ72axmhWT1R/6wgzwRshKt1TiMLc7EG"
    "a538sCc48K5l4KzL04zPoeWhYPss1Uux+nKrvQD3kyb1/6waWW0gaXbpG9WFa2KnjT72Uy"
    "ERfDhfCxyeYECeiyuUEy8cHfZVL54Njl7+QBt+6QWloAIR+6L200xVVnPUA+dKhdIsIwWC"
    "XDIHQ/qj0FOSF7kN2dNtz4+u3eR+Z9rPImSRNgEpMTBijXpBhd67LaakFBzvGIDvgUpgOm"
    "QBpmRngaYPnI41JHB7xR79Cyk5WXHnjT3vbCHmnAjB9GP83+/mn8RVr/9jT5G8+sISmxTG"
    "xKGKB0riVvlhVYPCkWZW9ZXGoTNfd70xhd2SR6vdVEa1MNbU0UwajRwyEHRgy9cSp3llCb"
    "rcknakKh8bTNqaJwF7AVUbtdyLvzRUXe0V3lTd5BZTkHB4IzzrV5onShojrYhjajOxjXt+"
    "0rSsORpRvOLcAmrTUAO1PvDj6WwYSZ6ITAY/YcYE9H29wH+Eq2tj8AFC8GGo3rw712R732"
    "zjNQNbggZBQ7yR0PkJdShpBeiDZ02PrOnmuaBAKwCoQpNkdzwy0ySxGEQ0hcMe9iKloH2b"
    "J1RT8gLPIF7Ck89NW31Nu+YwGEU6/zMvBX8LlVv1Veuo71NudJW3ASi3tykVNYgmMtNYEl"
    "dIpe1eGr6kdwALxraGXB907QKnxnaYp10m0JdZ50TWHeNc1Q3TyXc37O4Ld5nyUdNEs3VQ"
    "a3bnAIBmJ66LuyfQtGl3KwXNG3pvTuhj6P/ddqyjf/l7J9VkDL+nkvlgZmjqG8Z/1QfwD6"
    "T3ZFHeQJZ//YMHXhIQLhn3vVMIHQB3/MUIHYOcGfmeaG24CBPFWj7K7sQiIGDm+WzFb8M6"
    "DgD9wGNH8hW5cM3dlKT0WXuj3Xn+OrPMpAu4dGgi4SmLZQ1JLVu2zpT0VUEU0N5EiuIMxb"
    "IAdJJ0VRBUr7tp8htiPNs1ZEsWGS7MbiACXRc+f2lmUU86G2G94iUe4H7Qx+0Ir4PamSKC"
    "ISeka+B9R8c73f7wV2og/M9agmxxZVhJFeMbCIrN42w8FErkE8fDwivre6gWGQy2AjXJdm"
    "5EdAyAU32n0kgEDM1c6270R7qch9wS8D6pi424wirwz6juPog+9/IrSvzuFdIrTv4/I+7k"
    "chWGTjJ2x6NXPSACUntJKVTlmDXhBZaXXPRsaA/6WnyXK6GHMdaUY05mdhXoicS9YxBDVB"
    "1nEfIkjwEzByjkTPAevu75FCOYBH7FbrQoHqVqFZbz9Ln5eTf1aAaRlXWoSUN1YpHce1rF"
    "Kxiv/1JULW+WNK1EXJxBACcenMuGqwlYhl5z2AlItYdlymi/Oq2Kj26sqB1JHXJJmZJsw9"
    "oijVjTNFKlfsvMGUUSruhGN9qsuX68h09PyISL3UnMACoGrCjsK0ITZ2RJVGCp5Eo8MuZA"
    "htEHdlRTVahhBkWpEwJRKmqiLvlpcw5ayYSieV4Dmb4QwTR5JSBk6F7qwRm1RpFHlmTUAk"
    "WTLPckXTOU9dWSd/zK6S8/BkmdCx4+h/SbkP/kM3VDkQ0iH8fK65EE7rjiCmGs0MR+xGgW"
    "6h95qhOk05knIn8JGCpATF3B/Y0xL8Hx2iv6ENLQ9/5UyfGRog+UNrFlY+UGA0S68/gMvu"
    "jkeLyU0jOaw8OmvjHvCEGOjobE/xf19d9YiyxAnzgzslUkCCEE/HHX5xlAt0ZkejyrGVwI"
    "iqS1UpTP0AyuIwBXMNbMEArhOp5Vxy4ZcI2fXcTy2GU4a8O3Ta3ftu//au628K/pW0vYDg"
    "FPJOA2b4CJQfEkH/kLPc5RdZ1Jqi7+VdwrqO0kaXtkP8oztIUWg2nbjK3BsEjCej6eNw9k"
    "PvphOJpvQyELqk2oWYhMIW2IqR8hDaqvZQ9cjOyyBqD97KMPgYZuCgNGYY4aq0b9vchrsG"
    "6z1DDGSElrOouExMEsGwIhi2lgGRIhj24/KeXKkmaoVgiHQgkXMQ5xVP/yE5Q4JCI/wp7y"
    "nhDnEb1IW2+VLNmIXxitpUT5rDzH2OA/Z8B8r8i9tBOa+qZl9DY5bn0UWvkdikoM30rgWP"
    "027HNedns4eVa4DGgE0zQkc5QGOIjs2E4q3R4Y+UkMEo1QgddB8+nrZ73XbPciYrMPYrJU"
    "v7rmt/MtiePRWZsZxJ5GPDNn/a4jHwi15QUCXyDT54VRUs8oO/4/QmxRYeXzNEKZjMDSIx"
    "Vxbc+PmKe1vx7b0QCy4gtjWS9TG52EqIpPxiHgQRBQtzam27zn3KaV/jRi254h4GuYJ9Wo"
    "LTNc6AiXHax8RzjBkB9fXKDTWfJvPxdP4lbi+OsQPLHEeMUFvZ2qj3KZDvJ+Lej6Juaf/S"
    "FLQdO33oWRYAiZavZeCI3tt+p4v1sudmzvtiVZbaMRgpb9akznbg8AJy4a4N48c6g26MJa"
    "KigifWavuDaaOo228aIag55RiKk5bd/w7f+wbtNqo2C22JmFHZjT93C7K15EwN8u66FMvy"
    "rpu4KuGtyEEUVu4YV2WUljejPs6ZfhsuOHWQZfXVxsorPDofnd/Co/NReB+Pbw4Z1GK8T7"
    "MrRQg58OIUa3guKyGcYHZk4lPSCOWnF6MFub1VB1EDiaz0YQprW25VI9dYeEiFh1R4SDN5"
    "SElHUQ4MICaD1OgwomVF5JCmSmSNHBc5cKOUZL6CTxf6BFby8cuc2leofzuhSxfJw53c0C"
    "vFx53aXeyqDWiCjuboh9F4cBO/vDuY5DVRoPMkszdcSf4C2RqwYOVPLv0C0VoqtO509l4s"
    "yd/iur1ZUtC4bq+W5C/yMXu3nGv4pbZ7TmFp58YLh1LqTUrgQbm9XbKzJQo7Z51dsEOBLb"
    "8koLticomPe6Lcz2/SiLArE6Z4XWyLwq78cXmfUjY7VNyKXp6Iy5Wl2yvPNhFmKLy3WksV"
    "KsKckYP1qeeL2CVq+pa49kRNX35q+pbXTV0U+OW94BkX/pyPXqqU/biitWZnK1daZrnl+k"
    "iA9DzKVn65BiVMyzuZ6N1Bop6pqGda2eOdOgQg93qmMWdHnoU5I07Np/DQVz31WcssXTcN"
    "OqgES3AMY2Vik13BKDgEbX9XSnF2zrPztTWdGRpkUaHSudT5zaGf5bwOBmL1yjpfJPvHY7"
    "/+Q/j9CBFPSbWD+dNjblI8fhXMCBz+MlyOJw7K9AWdL8sITAPecwreJ7oE76MOQUc4Y/W2"
    "4lTXQzxxUYTxhcXMfIkXZ4OTJzvoOyVPZfimpUCdpfVyz42P1pWXM2Upk2h5Zo961wvqyp"
    "F4Fc5p5jCNOXRyxbiU7vTDKblz8ibvXh/V6xf3+Frad/Nb1nTeECVnHl+M9+pdX3EUqg+e"
    "s+uwLFPefISw9KT5FAbzlzQvwmg+1qYqwmg+Cu9jYTTZvMYXu4sLFHWr4vXNnsPHX/pe0Z"
    "2USky1zJRgyT9fYiatCrCiflmvvrsQugZ7CokveSVXchE4AfmQg7Pr2R2m4kuJKd+V2pd7"
    "bf86V0c5LaSs/vEcc7dLy9suq91hFPsMmds1S6C/4rZfRE59OTnEOMsSHMQYT884if1fe+"
    "UkYaI3+F+mbrB5Y4Ovn49D2KXP8PHBSKzfQTOy/mSXkvqTQqBjPzwr2sIJXkHJ9KZmrvDR"
    "evp1QvSEh9hwqfN7QGFfHiRalwdR23Kw0cWgTjc1YoS8WZZxvDsaXBCKLMzMGOtRl9ZsRT"
    "8xSu6Y39G6yLSsJOyJfqPXD+7PCw5tFuYHVNwxPnIkQh1LSQoN9zvTojjxVnZnRJ1mhOil"
    "2xS9dEtDUPTSTQQrSy/dGrdsPZvr84H3cAVqREAZzsT2CC13bA+L9aoG37T7H57hIjyIcD"
    "bVV28T4UEfhfcpVXaqH6TiJEy7Ge4iFOXK6EcsktxHn9QziiEfLhQTuFALJ3s+m0zOrnSa"
    "/Gdfnz1olm6qeXWKLq0++rUd6thUrl3P7VLRdIJ1UPLWhWBiOeQfLeSj2A7meIUDBPIQDt"
    "s8X+M99PANU5X36MTIO9n/EK3TwJbrz5Zi7/660G9yIg3cURASVKEOGWqehz/0XJHzGkU1"
    "sBqeSw5RqEHeOD3iIuf7OtCKFO38Aa6LOShuCqx8uhiXW35ICwtLHOwtEwnUAu8a29U4RL"
    "eGdjNWf7pI6CkKOMa0nZj+dqlVsTZl/KLAkk4OrrI/ItAvFOVkWRrk1nn7QujhGyb7gukT"
    "FmJecKLY4MhH5U1TTzAMQnWjiY470043NLgxcG7yhj8Ak7Eh+IGSN4LQ/DnU/OPzI65TJU"
    "ROxyjTdCquNzFimBrQiSIiHVo5MYQo0zhc2rLLtz0ulvPp/MtDw32xMWbP89FPDw30Z2NM"
    "vk6c++6LjfFpMobq3UPDfUHpTi2yzCG2JxGnbErAf4S2moaAiij+VEFf+lHyYzQJu/2ZRn"
    "YY6RV72bGe06V0rcNOcvpTFCMTiiiDIhoIXvkqBGt/XP6Ap9UEsFmFqQCj4Wo0HE840QBw"
    "5eu8EhBT1hj0gHgp+CLKisNxdVXbH0wbSOTv0jftPUNZcaZEcveX4tpfpmxyrzUwm98R/2"
    "A71Oub7lOzd3nGPzlbf2f67HXih55NYRf6Vln61rmWQnTaxNkek9fXKybj6Wi4ni7mQLXw"
    "X2+M1fPT02zyOJmvHxrB643xdbqagkvoTxaNok3ntk3x2sZyjHxMWf3gccpqOmyL6VEdOX"
    "cYcCWQVhPYuy4FrnfdRFjhrdrXOhBO8JqlsX9IY0adir04Nx4azt+NMVo8gvN7PRk/NPyX"
    "4OpwPprMZuiq93JjTH59mi7hNfdFljM+5/owoiJAU1QEKA1BUREg2dUiKgJ87EPzRTfknf"
    "6fTMyM0gpmlt5apWZN47HMRrwd2ZmmvVvlpesUyatS+4CwwZWJeRFC4TgS8aGcuOVEfOiZ"
    "+FDfA0faCApwZ4ZGri6Ykf3uYzSqL+80pGULfaN6muz1/FKEU3NTq7MKcDUs6tB2rCX5Il"
    "XF4IdrpkS7+JyPVAiAZAhRCHG08Czoo3myFLhopaMhH45v5yKVFdnSJO2gH8HvYPPSe1a9"
    "0AD07vnj6XDYaXvNsCVLe9UhKF50O/M3SBiL/su8mLsd0NBOB+m7ftTtTF8iMoaIHOAwco"
    "CwNpgAJ9MLNSJVFXaWB3ybgvoarI9U30GMvipu7DS71OTXNWaS8jwvPzwOf/0bZpaaLeZf"
    "vMdDnprRbPEpatWN7OdME5xAXK7tiPPJTTg4mPAm0wvIRRI2N3inCGpsZ2fqOGLK01viRO"
    "JsbomzRJtdVKG5FF4w3CQYjbs5TQsmQTbAsFxN1o3582zWpNk+crIkr/zR5yfwKzVOtw1a"
    "iNP3SAq0CUrohSh/RiM+H75641UWXLKslQAqjVnzXEZ6bsY7PEW+OttxsQY8c783jRHcVU"
    "lWu+DuTaqpDj0HvrpaTBWBV8s8HZyQH1vWd+iDYva40GP6UQKfrn93ygyYli2ZlgoGAxS/"
    "+wX6t++SrO51w7nqlXEPrtbIwOQX7VXbW1i696UHK3V2VaeTm6o6TZ2cGp38BQQkW6LC0y"
    "HGkuRw/ghZ2RkrXvdCpY0cWj5zKDmBRap2aBInOsl5E51YfJsLFmsqSoSMV4zBv3K/xwvS"
    "wVdmQhojy4R0rn5ZItBwp2l3upfgTQd4GuIxyENnQwzxFPt1mKjMGOKm084DVl3uoG4ebf"
    "hvu027deQcWYwdu5Hz8UzxhIDuipUT/MMzsRR4wwkwAACrfcqT8Tr1FOran0hpQWkEbB5Z"
    "+ojWOB+rrv2JREuiJimYJaKisHugyAOUH8EcXt6y2oLtZAeyEnQH4F4ZCZiEtE1mzoSpyu"
    "9YlKgVyupLH4oVL4OKcSWqx7NHNpMHKH/phLfKCi6dFFeMb7e51Efgm6u+eCPWZTHRmmfD"
    "2wuFjyZqCrucB0NvnMqfKtQeHfJZS+FniNkcKwp/ITsTdSIBeb++wCMBIXWjti/0QJQRFh"
    "+KZ4dwd8Ab9c5hDXl/mo5/GP00+/un8Rdp/dvT5G+XsQePMkF91gLfTl59wq6ulcZzCGQN"
    "wiwrre5ZZMH/0tNkOV2M88TWmaV1hJZh0kJo8560ypumgI3B0sCPgwV/qg/x/T3cnwcD2K"
    "9xq3WhLHKr0Mzbn6XPy8k/8wcXIlM3XJXOwG+KeR7XvCetuxvEUibcxLCc02Dok+ZyPdnO"
    "pHWx7BurtVTI3sEdA/iY8QjufGb9daIhHAUyNSTC1zGp4iIkpJkVEB0Ri4JQwGR4Na33WC"
    "CEoxs6sRMiEKLqJq+Uyp6hCUDrRA7TlO+rT+TR9hZpl2ofXhr0+nw47kMLiwFynCof0LMv"
    "i3BIRLASeMKXNQIFpyp/UpMRFgEo+dujiEDzGYAiQiZEyMSl012ETHh4iZCJj8JuETJRFb"
    "+vcM5XgEkpznnhIxY+Yl4XSHk+Yj/V6QKbLpZcxYV5pcBAlULttsOdbO2bBGutc+MmzUYr"
    "w0cKbXiFPsHhPvzKmryTiK1vAwq3+v4f0WpPflF+Q/vLlsB3eH3VLMr+TCr4fsFvTazohJ"
    "eyckzC0XzYOlmEqdMz+bDt4nMpbqE539kBH+GK3R2CZkzN+KaU1LVp/rxeTlHPJu/Vxvi8"
    "mM0Wv0jPT5LbuylyYWN8eZ6OJ9Lop8no54dG6E0Ws0+7R2H1afeSOxH1ojafYAfIyEJsgJ"
    "LNbbVo42vr9o7JtuwTVKV+VsSU2aOZ1OCpZFNmjzCtj0eZVE02GcYQSbnTOCOOPSqTcC/F"
    "JNwj5CSKntLJmPJklfJ+9pkmBF7VCck6sW0yBNJKrpJCuvnB2fsf02DctQOaa7a1Oury31"
    "eaedrFBZ/MGw/VvpOy7UTxjGoUjBsPgVzsPWXvPXVuAfc0fF7Brm7OX5aWcFnkzZwbwO3k"
    "o79aMp3zxAF4clR9yPUmWoHViZlwU9xlE8OjtIKZZTOzjrEf9LJjXbz+HyPI42OuUFFwXR"
    "RcrzHkoste3uimxKyILnte4ANLlz1RsTtTxW4ilqKE9EUlpH1MaWJxtO+acWmjNxQoMvlO"
    "V/qcowVffFiNA0pSbI0P2ZkAGylgUsHpj7IX8oM+0eEzimJx3ssifKXE8JUQT2JA01ml8R"
    "HKzupajX6ajJ+Rfdl/uTFWKGBlhYJVxpPZ9OtkCZ/wXyZZq1c/T5+e0FjOi43xeThFgzt/"
    "ObBc+4soxr50bTtMJ4wonBlRDvL7zpQJe98/Vos5mZ8hkgg7nw0A7O+qrtg3jZ1+tP/gWV"
    "YhcQ/+aIxxsX5y0dZxEY7AAaL95DTLMi3mFGGcSjj/hTm35juRIyuyimFhKmEnSW37dzq+"
    "ScfT1v/K7K3/EkYQxj9685SvolyayOONw9/0prUFhJfueatKbPLlAOITGHMVGZK7aUsLZ9"
    "LqZM50KtKsEEOcYFwgcSXZxBD72dcwNHhG5qAUgzAslGdYMNSD6QJELV2HaEotv8NT9Pmh"
    "07tT36RvGlP5KJxKJEUER/3JZgYzTCOgDGbmTrZfTJLglDIvQzSVVJ/zD/RGLkFwMLPtlT"
    "hVJaEsZFLWon5THlYzUahJWHduzlh3UNQ62EkyR7yHaEXAXskBeyKg6UYENPEX0EQTMBKN"
    "SLhS2Ag/ZqNCo0YgfrD2qqH+w9w2CbYd/IGbNMPO1n9U+pe5vYZVB3yMH10QlGH5vYnaQR"
    "xd4QJdQWsyuURLlOBcfRbwNPhukD69QAv2cYRve+MmY8o2rD1vU366tofdmuFwlmZb77Ba"
    "zKXfAgi/R00Cn6uDD2b+Gog65SsIU1tZpjZdBfPKtFFvFEbLBoG0ioa3NpVW3k5Ry9txvT"
    "y8iLIERoXpyw6LWoyWDw3wz8aYzR4fGuCfjQF++PqhAf/dGMPZcAmuoz8bY/I4nM4eGujP"
    "xgDC7VAaT2YTpxgQ9raZhVm3NLy6TWbVbaxAR/XSqv/5PHl248dwTjk3HhrO343xtFyMJq"
    "sVqtgTvN4Yy8l6+Zv0y3C6Rrewt0nhbHjwWn7J2Plz1NJeNKfQhiN5MGxpBNJKWsfyNzQG"
    "yLAeyVFKEVuQEtKByZkxmNONKlFaYTHjzGIGDgsrG2txSmEtKzu9VZSGqA8z1ZOF7ELSni"
    "AFJp5qEapqHWqddve+27+96/pnmX8l7QgjHVfQvKCYJ5L/MUUiwKiuZztu8YMcFNeyoUeg"
    "/JAIiiD8PIPwHVwSq36utb8SpmOMsCKYph1hk1/X2OkVyxnxT7DZYv7FezyaSBIB2FCs9w"
    "M89xMTdFJAJhELoIlAR+3ljPIZgVyIaCWLaDHnAyNPSfSCqWUrUSIwqJ5mDlHFi38+Uq3Q"
    "g2zBPG/oi2JOLIuSVktB/gjlpOoMLjfBV/xECd1cUkwqWM45QBeLGKoshrFd7oIeZI5Jx4"
    "uLyh7EVl10C41jm8BYpK+apb/oipyUpxh/6CYtns2Jb/oeer74mDYsVAt9ATQVThY4/NGa"
    "CwnH1CFa4Z8g7Uzz2+mAfihVvFiWmDDsA9EA7/Qf6BD7YiKcR6f9Jb8YBnGI6DQeo9P8CU"
    "5t3vVXhEi1C/Ls/c0hS4hTiLzsSLTV9Mv8+emh4fxtZgD4lsZ0fptsOb+NV6+BhSRV/VU7"
    "MqXgRciqOV3vuhRo3nUT0YS3IlbyzDa+3K175eVN1MJ44JnQWd2bMboP6dyMyDgsCyFCKq"
    "xoZdu5Q/IpIysjpIKVZbNSuCyEy0K4LDhboTFjb7K5rUgL06OmppiWQndv0mxKe/+5a+RH"
    "xrvDR9sGoJ9BvHM0T5aiSaZiIbuwKJdVmpUE/Y1BnKx7es9XU+ksxEYCPs4ZnwHGME1FYr"
    "GuEEiomkdN+vdJNmzdZkonjRFWEtP8M6+g3HCUDpolqTIB0MRtNEZXLS9xbqo0+PVMgf3u"
    "4x8ULeg7Ad9jmyIMJ0R8RAnTZGEuoUzBCcq2oq6V0AWFLsgHH+msNTw0oSxjbZYSw4arg8"
    "x4E8mrdQaXG9dWar+/8nxlxTT8i9g2LodzoVhVC8eKAklcoRcEvClvsu3ljUnO4BeGvgHd"
    "0n50Blyh8SqFN54e6psBwfFmXwpMYHycm3wL3+moHHfmpTX+AihWYLBqbW0YFuCyBi3DKI"
    "IO2kz0/GbJNBh74ptjKoQTk5mfDOlePhzgZyciujC0tQn+yYjrYzB+ddZiZo/IGAaQpXpF"
    "xm6IGY1nRIKmwgLcI0EXEGSL9AwVR3ejwJ0lMV9KnJboNgndFh6TsjwmGH9pLVwY0YXWLb"
    "6CywjmLW/SZ4kY9WjLDhd9XCznqMCd+2JjzJ7no58eGujPxph8nTj33Rcb49NkDC0PDw33"
    "RZNuTmMegLTZ6jkA7hPt//cx87/8TTMyGKPCdMLGyJmNURiP68pYYXOse95srdHlJnGWI3"
    "Xy5pLMWWGWvdAsW3YwH7KYpaqunk2NSnX1rXlX6mcJlZagy0FchRX6Z1n6ZxbpL0xXTdmv"
    "IrIelYN5a6pMEW7e89WMuyykQalQhGqqCIkoGv75KKJoOBEUiH5fVqxjpCJ6RpgOhOngmh"
    "u+MB1wZTogb6w5QIkn83G3o9ICGTsxmKO5rmOCQZE6qSYYL5aHygTjRxHlHT2AzzHkBY2H"
    "CQSXhemlDNOLcGxz4tgWqn9NVf/SdZiPKmaXJ+NwLC2mCzklu5nG+vGwk99Xp8Nhp+01w5"
    "6fwK8Gf5ey8Y0k8qQTpEpAqkMqHSGtZAA6yfKIivVF6UdJM+DXQPijXnbu3q0ZId+Uu6tv"
    "38Fes9eNWglJzc1JuWu1wb+9Afy331Yam9P2XlY3J7W1HTTgtVYX/NtR4R3wB9zZKgq8dD"
    "9oUZ7XXEhYtm7vmOpR+ARly1VRJgAuASbI8iCLuFRIdYXw4mERmcJ0XAlMMczBHzTl2/DN"
    "/b3iXKJjQEWEKCq7u7s1MvI5oOKby/1+D6ysvqJ8cC7jR2PkRDPNnSYbCUcaRhhh9hZQFs"
    "VfsoAAGCyrrRbg6UB21m8reqSpdz14p33bRq+78H5Pgxus2qc839KOqsVihjH90zTaK+z5"
    "8dMEbLiI2+Ah3U5wDdRSMY2twBYUMCA3MqzAGiuvdfRbx3ivopUI9mB04Lb7SNTpfeSJEE"
    "uvjGoj7K5v8gDlOmWxmQA363t8LwA7c68HL5E2c85VkrTaCFHVMsZJZvPI0Bunvqyj9seR"
    "Z/oFpQHA0Uxqxs2SzEy2kEzBwFc/dovX+/NJhGa0XXm4rsBKUcFoTYK5KvbMTZqFynCfhg"
    "1ZgseLtU29WqjVDexdXGd7U7uPZle7A3cLVQMnvqzdgm1CGbRajemYt738JsW85HKM1rjk"
    "Pl6+aWl7C/dlpaW00SZ952g+3WymJSrLUophKWpXIjb9TgaVi1bfcI73XuBZ178d+JjKSi"
    "sTph0aTDvJmHbisc2ytZVeJcvQCaqEpuh7eZcYNRkijGoSDuWP7ghXBlxtoZMJ6QxQiQfg"
    "b28dqaOP5A25h28z23tl8MPr3x3V4m8Xq/njyWj6OJyBGXxzG1HkPR51kxghZ+SDXCE2KK"
    "o8cPYVbtlwIjT0omHDidTXi1c2gF3eEcj5Y8PBMm0NSOlZdqYYLVfs2HYQxgpUhpSB0ud8"
    "WwrAZN6ZoqS8s4HnbSnAknlnipJyzwaOt6UX2c60JWF0XDEAgA6FU6Uz4HwjciBk3oTCZP"
    "wCz/PW4yDIvO2EyTgGnufNRt9qVrbtBqfkC35kPASwOlMd7TedFu+bjwso+/aDEVaDEVxv"
    "Ri6e7NsRRlgRRnC8OSnyTtFPe2mfzXYUJeaLIZrjYB6cVc72/HAhg+EoQssvD1J3JI54kM"
    "FqFKHlmAdpm1HZPNAtWA05y1YUoeQLf0U+Kxjxgjzz9oMT8og717uOBx/zloMTcok7zzvN"
    "4c08gv+t0zHbfkOk54sL9/fcyz04iuyWaQI5jzzgegfCQWQ3SxPIueQB17uRacvHY2Y9jE"
    "TOFw+QBLod3PG/I4WhZN+Q4tT88oHvXSmMJPumFKfmmA8870xHU828LcVoueLBtjWAkRSd"
    "bb8aO1OAJvO2FCXlnQ9c70wBmMzbUpSUez7wvDN9120ZJgDI0glsMLKWYYNKGoIvvmjdLo"
    "r+gt7O7YvSGJ7bqTan1u1WeW0shxPOWMS8cyWMwD+DUrcwfhnEvKUljFABBqXtbdwwyH7T"
    "IbxaNgGMQM0VY9QOjKhXet2uyxjORbAwnsxbWZyYd15wLYaF4WTeteLE3POCZ1HM0rfmy0"
    "7+rmd03hHpueKIk+G6VV7gQdJrwdcoex0cLdwrjji6zPsWibxKvOF6F8PBZd7HSOSV4g3P"
    "u5qhy0rWHS1GyxdXkKrvRqqhU0bpaBQhCo15yeJwACvzNhYlrQZDzmxeHDGEee+KklaEIe"
    "k7VukM8fRxJdu+RSLnizFRXX7Eu/iFQZrZAKbwunOR+MG1yIUhmtnepfC6cRH5wbOY5SGq"
    "Igti5h0rTM43R8aU9nuO2JJ52wpR888UGps9R0zJvHeFqCvAFAo7/fWZEqv/llxprMiyWE"
    "HhsbF51JqEoliRJ27SSmId/Wcl2PuVrm1Nc2FoDVv+phkNSNQ4aFbD0l71o61ZmtoIxrxp"
    "KPJOg6W2Gqr83pANtbHX5F0D9jn5Mcq5/EYlNs9xhrL8sm7wMyRYLRPxnNRLp0bluryLFS"
    "nBhfEmstuBq2SUMaK08qgUW1wM98x7HDXyaVvUcD2JRqSILkN8dBlCG1aGar5hOq4KOdNv"
    "FXWpzYuAwU30obOCuTAvgVh0GWIophs9qHHkMzX1jBdr5RN/2oq4hCnGU9chAtypYmqYKV"
    "SiqlfItYAui0IG5EQGfDFNFeBHak2bXDcUI8pHvikc7YKrhKK/DBB6z5csHWbEr5CmSFv5"
    "qB+lf9vvLDhiRFUFM+8ywPAHv75L3xSZYMhK3DsjVBWTpjrt7n23f3vX9bdP/0rarhnvG/"
    "Mn+HWW9MpoAQxR8WP5y0UrvqgYIyOKGN3FOHJmXnCB7N106Is5wRJxjBj6NPWchyzwycc3"
    "Zvh8mnrCl6HUMyOAAVFNF/Adwww8nl5l9sMkRFXPWci0Bzp16Vh3wYCqnhDe30Rb4NEU4G"
    "IQB3GichtelSYMurWAGCdfiKqek49l/WJlTBjmX4zug07BcMUFFvgiZB8UPT8xnAE6jOaD"
    "4hbNPmWAj0T6QVG0NFs3zB0AggE/nOiDIrfVbFkCqoRpg1/Khh+J9IOiGMrGZBRhIpT1FG"
    "PusuaTMYIZoxVw+jkqjFBidALGcNA8I5JR0nqCec+gqYSjeDOCqZLPmw8IpvJm7jQYVAok"
    "Gea5GSeuJ6BMpkTZlrL4AzC6esLYZYARjGwcMwEZoRRQHjULiDSvEvw2LD77KJ1w2+N4Hv"
    "X/MMWSROkEnm58u6zv3qUXS/s3C5o4VTWx7FFA2UtEshePvrZetYRA+KS4a4+i3ObSpc5F"
    "hlSmkJ4pG98ksPXuj3G8P7m0n39eajs/cpcckBuP+1yCkadg4KtOYFiSt99CWf6qArPN7l"
    "A1DAWm/8tKu+d1sN92UMImavSkdvuohAl6s1VQc977QavJcsbFgnuxCX0CW6YUDu+9EOzM"
    "0c+lyQDp+IDLGgz2hYHP4Ifotq7lNh2nwdgTOPQ7nxtqIk7XDen2Fy1VaHd4iZ8J8UbR3Z"
    "K/2yCKXEO8f2+q+vGwkxF/CVHlTYAE9gz6LoZZ5wRBuBvetWAn394A/ttvwwp023sZ7nqt"
    "Leq36e+WQYruJfshH2HmHm9j/Er2ggQUJUeiNqNM6bRRhYFW98dGG2W1g/NLbd+2Gug068"
    "KbA8UpaQNrdCl38oCJV7mZ/xVLgwBlyJvDKbnKnIuxA1sjLdQpsn3bbjiZ685jlPDXN9XO"
    "3WaZs+xwOg4WItPuyf2GGQ4UjB2QzMxKHoMDxl1VCeAiwzIk2uA8ZE6uHDsjkeW9Gi5B2g"
    "RNfHci52aeWWQ5cKfktFduNOwod5K3I4xTS3C2LaejdflptEvtu679udQOpnUmlRZ78ryu"
    "5YBgISLwx6fKWd+CVg2kSIVTu6Pa1O+E2zXRrljDbErWiWopndPzoL7CtqhrcU3JGdlyWV"
    "EOEQl0GWRa74i5UGR6dofhD2Va4SY0gc7LnaLWStVrrSRAThASk5mTLCSiyRRY5X2CguRD"
    "ojE+Jib6T9uyfToKQbFEQfF0tM29xFpiJEJWSUd8p0cTygCeSi7V0ouFM6AShvLePJHU/9"
    "QQsAhlTROc+wwByAgR8PWZokMwompG2ORfQQjss5bNXI4Tp6p7PU7NUJkRCtNciA9fEZuE"
    "cqXOUU1ciRQFS33q6y3J5nC0nn51KoziVk3nxkPD+bsxnobPq8n4oeH83RijxePTbLKGl/"
    "yXlM4BbCEPKNbxIHEZD2J5LSZpdqbUATOJM7Map3OPqgxYL6UMWC9eBsw1k25NlakQWISs"
    "XDxhyfWOBnsMDu77WCCAY2iH/hO1Be3zfdSaU3npIWM97N/VbcMa7J1BF9xQ76BpHtrvG6"
    "jXF7yzve1nmeeF8OqoAN2VIajDf77cfMwmiSOy0kIot+Q+grzb8F0j/Xar0f6/ngjiEGbi"
    "HM3Ep4OakbE4ZQ6MLeEgqQtfY7GzHEZylJbILlwBFUdXuAJydgVwFILCT+5BFNEcI0fCCc"
    "myLe2141F+1aSjebKUS3MagDJiPzoDrtB4lQIdFzIdWzHAaAc1Bk1yErguBQiNOvIGXftJ"
    "YdUEyW/dlEcajNc0qjr7XkRLh1FMuaERDaiqKCqw508hqWQrt5lQhXC5vjsWgUTtkvUgZX"
    "LLSj6Hi3DOEnzAomUaV65Y0RCMk4ZgwipWC+sJwSpG2HQzqfTEMYSGz6jhE44kEb1GNgEQ"
    "JxxPQWzxzHuCsERMz0+WkZIqBeQtHqGx36VvgNdweMO09vJO/w/Yx9H3j4evKbJhGroi70"
    "IPCJmpDJkpwrosolNkiLIlqPHyGYhH8N+NsXp+eppNHifz9UMjeL0xPi8W44cG/DeLtJR/"
    "MaTIeiAyIkFgilFWNGSriFjC6EbEgCuBVAArBPzaC/gf2e1dET56PzvGyJi2QON5AZucfL"
    "HlPCaXDuGofK5eKluxrkKpBgBi5Y3M1B+5wvBA0V8+aCdbVyRlB1uZvAAZJIdabTG41sEn"
    "jeAHVRi0nfZiS9Zpl+NiW4LRKoyIpb++CUgwSPaa6q4kaQ8UezDehdA8+gNWvbZfAkxH+U"
    "UD6mcOsyiAaoXGrPhUCgVq5DOVRJnITIY8Rxaiseb5UhODSe9dCklweRv24p8Wse+hzyYY"
    "+MiPCBNfGSY+xAAHqRjQdBY+fISyDXzT+ZflZDydzNfSfAgdn5ELG+NpuRg/j7zb4XcbY/"
    "XbfDH/7fGh4b4AVxbPy9HEfTj0JpNpkMbY0k62tbRjphbZ2xNoLVc+gbBXkQyBzHiSaAW0"
    "whRYd1MgQdJgPqqThhCefgZPP1kIu9DRX3EJ/ibi40+caVy7+EO2QBr1ADcdMukIEXtm3n"
    "qCE7HvQu6+UcAXE8GR3GgBGItoZR+MqJpCT5sqtbqdklrdJqRWh6Y4O5wemQBUSJFCihRS"
    "pJAihRR5gRQZc5HSyJIkvyqTRBlzAVNaoJt+U5C72z4q79F2Sn00UN2VrtOtBfzbeYGVWO"
    "66qFeL1oPVVfqKsjnJ6j28cd+FNUAUdQArhSgDcLvV2t6jqi0t1AamH7QfaamKP5Tau0Ml"
    "RFR0v/eCiots4Qf2eopTGebHqOWvKt+ZwYYfYx+8iLvyYWEu+ajZ0negNZCrlRNHcYv9eK"
    "UpYSMpmoGFWlBK7yeMWURZ9rx/IDbIFWuUPU3m4+n8SzO+0bh3Hhrui40xfHpaLr7CqmTe"
    "q42xnPxjMkKVyrxXWez+fQqRuJ8oEPdj4nD6emFQOc6PJLQQoSMXASb4Eqd9UoJYWvlRjK"
    "yigPaoAO2lANoj1N5TTCA8ssGJEQkwQz0P/4xELkq29hfB+rAGVxOgTR6iKkCnGRomv64x"
    "G4MH5w+Pw1//htkZZov5F+/xEPyj2eITeYM9WTsWoHGqihTjvDa0QHmzzO+ZTGgRUhG7X0"
    "LsvjCGfgBjqMiu4Z+PVCtUWLXLqiIZszgxA580gsBdeBNYNrKcvAlBncTUaZ4DvNVOpYqi"
    "m7SMuWpfGs1LSvfMePkmdH4YP+El72Ceg6xb0jcNrT74IRR+AJTaFuwDTl6X+x45ANCYXg"
    "B5zFxs6cdvQN//ru2cp5M/VTgJynAShGcEreEpTFMVcwhud7rrUpid7rqJVid4CxdesFWQ"
    "xdGCDVB2HgYssSIF1VYkp+QKehmuuxK5EC7KIpHrs2BPI3KnXov/MouHptOmiX1vJ4e+t2"
    "MmxGDXyshOfISy+TlazNfL4XQ+no6Gbuse7MLG+Gn65SdpNHxeTxfzh0b43cbwL/tXpvPP"
    "i+XjEL4ZzmCWTujtxnie/zxf/AKed19k4Wn+2TbCHcqjO5QoDzCcRUn01TyXCvHWaX/Znm"
    "C5B7Kgmb0aGGmgsre28WQ9WT5O59PVejqSgE7wPFo/L+EsT7qzMR6H8+fhTBrO54v10Nna"
    "YpcyHUQ0YkUnWazoxMQKYfqvjWFRmP6F6V+Y/nleoSFTB7PpOU4rjM5pxv6wHYkZbAKxQJ"
    "vBxB+x6Qnbftj6HF/JFEZ9zCwqII1ASlivoqFUQZWh8sAj4rigxoSjKXitOlAQn8l3mIOt"
    "aKO3k/Gted4RhD9/w+IVkjSXVlIgceGVodBnHn3+Ewwt3zXFNi3n68C1HfcgEZ8Q3p4yvD"
    "0e/xgdPhEyYVuLAZrBcimMlmnARjcNBmAJpNUEVhR1EmaobOn4oWP7oujF+DhCz84YSheR"
    "pPJTEKsqod+kxNTF5x2nafoh8M/L/QGXGAT+kEJXtKAPPwMDPZKwFyScxYV8jC7yoJD1RV"
    "WoioujIuNVZLxyDCY4R7WXF6D3ZMp0jZBWBdiSMlwPp+1OP76lqFCpW2uUPE2P4tkMTYId"
    "qkEiLfha81Fo8h9Fk79YhRe6+8W6e/5KO5/gZ1bXs+npoTDVuGcrNw9mzONWHdwLdWSmdZ"
    "Ai2DPONJxKtmqEejrFUicLalwdfGTzhpjUGrdhJD0k7Bdl2C/2sq28XRixHh2j7GB1twXN"
    "aDEO+tHANxtj8uvQ72oTvN4Yw9l0uHpooD9e4LoXrd6k4yauf9LkSrWTc6XasVwpB2PwoS"
    "/OHksQRjVF38s78rogkUclUof+R3ecqgn/48lo+jic/dC7cSL/gaSpO+ejh3c3ptEjVICE"
    "7ipCZK0+2VCSQF4Vzf4KblAnkSuT9hQhFWHbIrFC6MGiwHzVdeGEHqysiMdIBdIMVgdca7"
    "nQ3vCIDcYf4rSmhtiUIhsZ0reOfO03dYjKZy1iVE6wBdHm8Og0PW7S2ii8528yGCnCDZbz"
    "NVLEDBDuR/n19YXxoTzjA8aJGNi05ofoKJyWi3gcrkc/wZx598XG+DyczuAF528WS0MaUz"
    "yl7T5RZbuPVTGwLBjUy9iWC6eqiCPxCvEscGZmUpkwQqH6CtVXqL6ipoBYoYmM5E+Tro8A"
    "F9OjWTQUOp17YWhrE/xzFY27aM7krG8XoeM9WaZ6UuwvJ13VmqnaHfbkDaVed3CIpFdIdQ"
    "2NzvtA9DOEPleaPqfb2l46av9m0R3CNPnobYVjjfvNaPSGTrLa0IlpDdhsZkAySif8kCFF"
    "zDi9gP3nZGkWM65EYgFuYDN4ge2bFILtNzn0OExTFSivHXl8QqVXdPgdTshISrCQJSNMph"
    "ZYk7E+WJp0OmoSkLIM14RNCzSBVKCciLIC9DjWqRwhE+iS0VWt06v0Yppq2LHCBHTyCALz"
    "hKZxKiwsokmWlgFuIrFAOiEvzAb3LzgPk+gF3iLviSA2C6P3FYzegrHZGetnrWS2zRZhWV"
    "zJL5r9ntSqifjcDaVV8YhIiuvahNKr2Lo2keOfEDFaFjfRVhZ/JDZnij8qzJhlmTHDM4HW"
    "SBSmqYpIUXS3JmwhZInswQYoO6voaTn5Mh/OR79JWFsf1Nci+d7GGH6ZEChIVzfGZDaeLG"
    "e/BS2CIhc2xnixmgS3w+/AveclGid0P3IFPDOcguGAXChBWvAE9h5mSI2mT1PYQyr4DtFL"
    "zQyzq3NHY3iMnp4hu+Od6B5V/+5R0GMIWcVcYCVGWJU9+NpqnejPJfpz8bcKRH8u0Z9L9O"
    "f6CJF6wqxYC+sT12ZFsUIvWaEiH5iTLFWRXXnN7ErR+SgJc/z8Ng1VT3C+skBCcgWMvLGr"
    "NSdxN3Ue84UEThWLz1+pqhppBlF6n7Apx+qGkvDFUFxttfCHNm9Ci1B6tczTARzl+FXTUs"
    "EgcX9V8MQ3cN2h2R9kSz9CogOcVaYlPE/leZ7IjMUBX+3l3S4RcvIIFZO7bjv3dz7u8E0a"
    "0qvH4WwWL64SXQ2ZcfTJPzSI3oaRxWIWH6Vsc1ngrwPa0vp5FfbgOVccv914+NvK8dXBV8"
    "613ybDpXsRvfR8amF/muNL871vzjDYW+TJg2NArwxy5HlvwKeMHXud+/hy8bwGI5Ouhv11"
    "4BeswN+wv869lMmIl3taC+moyTyhiEOVPasm/wTg/3NjzAATZmv4dwJfAC59AVe+rOHfCX"
    "wBrnyarH+ZTOYPDffFxvD5dwHXcq4G8V3eAalkrxN8EanVJjG6epaZbHcZ6ky6eMh/ZcPR"
    "oRM4uniwlunEqSpZnaSQvC3wa5hw9J6vJIK3NOfZbfJ5dhs/z4Qno56ejARl/4LCEvFhKq"
    "ZL8FKuMWoIudAYnhSPzB8fMhSViE86nro7ppg4KU13NH0eE+AosNtj8lwVPR+rtB3dpFjp"
    "RM/HHOOyRM/HvNsUip6POYIpej5eI7dX9Hw8A7vo+Shyn4VqL1T7SsrSQrX/UKr96nQ47D"
    "QonFO1O0x7/CZNuT/6hFdrdxj6SOMECDRncYu+h1zuOzcpOry8N08G6XhP88cFRDV1xnUY"
    "nHHCfXSR+8gVxF88rBjtSD5dJeEsqNtClVuZhruWNmM417KnqVCzaqpmiRSi64o5oVMlLq"
    "AyQ588hsCeQbVN0BUu1GsDbWkeGpQ/FtBqtcmTTbQf5CtBrkiTwRpo2PJBO9m6MtrJR2fl"
    "RewEsWdu0owDdvC0pMDHKQ0Czc1JVvqtzUnptPsN+KYF3mw7cm9zUns9BVxSevcquLS9RW"
    "+0Xh+86SsKeFa9h4RgN0FPdcENpd/uwX9bbXjjHo2o3cKnBq0WfOpOHsBnt90fozJZud+E"
    "pu2Gqh8PO/ldtN0oPWuIrV3fRY36ro/xFWIQwhOZAcgoXVX8u1cILha6XU11O47qfAjGXq"
    "98cKiQliNFIqFKf3FdUhcmvMeEbpKwx99soKoIIO90+XhpRYAoHkM4aMVAuaYC4eBDoUX4"
    "QDKoElKIpTQKhdKSFV/Avh8gaXug9JHkDiXzngrF8HY7SYrvduGNjgplfUXpIvEfPtQZdB"
    "thJQFc6qJB1G4PkKt3LaJWUfbXIXpWYyDDJw3T2gOs/wMPDcSnuFeV/IjQQ0rxqXpriVZ+"
    "9gmE4OyDGJvQDHiSaAW0Qiepl+ga10niJzTrXp80gvB4MHg8iGf4heb4aisCNxFrfNI0Kz"
    "9877//H2vMssc="
)
