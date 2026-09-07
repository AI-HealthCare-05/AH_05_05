from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `badges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '배지 ID',
    `name` VARCHAR(100) NOT NULL UNIQUE COMMENT '배지 이름',
    `description` VARCHAR(500) COMMENT '배지 설명',
    `on_image_path` VARCHAR(500) NOT NULL COMMENT '활성화 배지 이미지 상대 경로',
    `off_image_path` VARCHAR(500) NOT NULL COMMENT '비활성화 배지 이미지 상대 경로',
    `is_active` BOOL NOT NULL COMMENT '배지 사용 여부' DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL COMMENT '등록 일시' DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) COMMENT '최종 수정 일시' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `created_by_admin_id` BIGINT COMMENT '등록 관리자 ID',
    `updated_by_admin_id` BIGINT COMMENT '최종 수정 관리자 ID',
    CONSTRAINT `fk_badges_admin_7205d3f9` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_badges_admin_f1c4c10f` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    KEY `idx_badges_active` (`is_active`),
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
    CONSTRAINT `chk_challenges_recruit_period` CHECK (`recruit_end_at` > `recruit_start_at`),
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
    UNIQUE KEY `uq_user_challenges_user_challenge` (`user_id`, `challenge_id`),
    CONSTRAINT `chk_user_challenges_period` CHECK (`end_at` >= `started_at`),
    CONSTRAINT `chk_user_challenges_target_count` CHECK (`target_count` >= 0),
    CONSTRAINT `chk_user_challenges_completed_count` CHECK (`completed_count` >= 0),
    CONSTRAINT `chk_user_challenges_progress_rate` CHECK (`progress_rate` BETWEEN 0 AND 100),
    CONSTRAINT `fk_user_cha_challeng_1f41b58d` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_cha_user_a9810390` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
    KEY `idx_user_challenges_user_status` (`user_id`, `status`, `joined_at`),
    KEY `idx_user_challenges_challenge_status` (`challenge_id`, `status`),
    KEY `idx_user_challenges_end_at` (`end_at`)
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
    UNIQUE KEY `uq_challenge_progress_period` (`user_challenge_id`, `period_start`, `period_end`),
    CONSTRAINT `chk_challenge_progress_period` CHECK (`period_end` >= `period_start`),
    CONSTRAINT `chk_challenge_progress_target_count` CHECK (`target_count` >= 0),
    CONSTRAINT `chk_challenge_progress_completed_count` CHECK (`completed_count` >= 0),
    CONSTRAINT `chk_challenge_progress_progress_rate` CHECK (`progress_rate` BETWEEN 0 AND 100),
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
    CONSTRAINT `fk_challeng_challeng_e3ae9988` FOREIGN KEY (`progress_id`) REFERENCES `challenge_progress` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_challeng_admin_219da39f` FOREIGN KEY (`reviewed_by_admin_id`) REFERENCES `admin` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_challeng_user_cha_68c6767c` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`) ON DELETE RESTRICT,
    KEY `idx_challenge_verifications_date` (`user_challenge_id`, `verification_date`),
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
    UNIQUE KEY `uq_user_badges_participation_badge` (`user_challenge_id`, `badge_id`),
    CONSTRAINT `fk_user_bad_badges_117d2f2f` FOREIGN KEY (`badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_challeng_d482ced1` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_user_ad1a864e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_bad_user_cha_e64688c1` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`) ON DELETE RESTRICT,
    KEY `idx_user_badges_user_status` (`user_id`, `status`, `awarded_at`),
    KEY `idx_user_badges_challenge` (`challenge_id`, `awarded_at`)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `user_badges`;
        DROP TABLE IF EXISTS `challenge_verifications`;
        DROP TABLE IF EXISTS `challenge_progress`;
        DROP TABLE IF EXISTS `user_challenges`;
        DROP TABLE IF EXISTS `challenges`;
        DROP TABLE IF EXISTS `badges`;"""


MODELS_STATE = (
    "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"
)
