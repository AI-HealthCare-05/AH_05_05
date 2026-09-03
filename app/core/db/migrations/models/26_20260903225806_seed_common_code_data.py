from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `_migration_26_common_code_seed` (
            `entity_type` VARCHAR(10) NOT NULL,
            `group_code` VARCHAR(20) NOT NULL,
            `detail_code` VARCHAR(20) NOT NULL DEFAULT '',
            PRIMARY KEY (`entity_type`, `group_code`, `detail_code`)
        ) CHARACTER SET utf8mb4;

        INSERT IGNORE INTO `_migration_26_common_code_seed` (`entity_type`, `group_code`, `detail_code`)
        SELECT 'GROUP', seed.`group_code`, ''
        FROM (
            SELECT 'P_REASON' AS `group_code`
            UNION ALL SELECT 'N_REASON'
        ) AS seed
        LEFT JOIN `common_code_groups` AS existing
          ON existing.`group_code` = seed.`group_code`
        WHERE existing.`id` IS NULL;

        INSERT IGNORE INTO `common_code_groups`
            (`category`, `group_code`, `group_name`, `description`, `is_active`)
        VALUES
            ('CHAT', 'P_REASON', '챗봇평가긍정이유', '챗봇 평가하기 긍정이유', 1),
            ('CHAT', 'N_REASON', '챗봇평가부정이유', '챗봇 평가하기 부정 이유', 1);

        INSERT IGNORE INTO `_migration_26_common_code_seed` (`entity_type`, `group_code`, `detail_code`)
        SELECT 'CODE', seed.`group_code`, seed.`detail_code`
        FROM (
            SELECT 'P_REASON' AS `group_code`, 'P01' AS `detail_code`
            UNION ALL SELECT 'P_REASON', 'P02'
            UNION ALL SELECT 'P_REASON', 'P03'
            UNION ALL SELECT 'P_REASON', 'P04'
            UNION ALL SELECT 'P_REASON', 'P05'
            UNION ALL SELECT 'N_REASON', 'N01'
            UNION ALL SELECT 'N_REASON', 'N02'
            UNION ALL SELECT 'N_REASON', 'N03'
            UNION ALL SELECT 'N_REASON', 'N04'
            UNION ALL SELECT 'N_REASON', 'N05'
        ) AS seed
        JOIN `common_code_groups` AS code_group
          ON code_group.`group_code` = seed.`group_code`
        LEFT JOIN `common_codes` AS existing
          ON existing.`group_id` = code_group.`id`
         AND existing.`detail_code` = seed.`detail_code`
        WHERE existing.`id` IS NULL;

        INSERT IGNORE INTO `common_codes`
            (`group_id`, `detail_code`, `detail_name`, `description`, `sort_order`, `is_active`)
        SELECT code_group.`id`, seed.`detail_code`, seed.`detail_name`, NULL, seed.`sort_order`, 1
        FROM (
            SELECT 'P_REASON' AS `group_code`, 'P01' AS `detail_code`, '최신' AS `detail_name`, 0 AS `sort_order`
            UNION ALL SELECT 'P_REASON', 'P02', '정확함', 1
            UNION ALL SELECT 'P_REASON', 'P03', '도움이 됨', 2
            UNION ALL SELECT 'P_REASON', 'P04', '지침을 따름', 3
            UNION ALL SELECT 'P_REASON', 'P05', '우수한 출처', 4
            UNION ALL SELECT 'N_REASON', 'N01', '오래된 정보', 1
            UNION ALL SELECT 'N_REASON', 'N02', '부정확함', 2
            UNION ALL SELECT 'N_REASON', 'N03', '잘못된 출처', 3
            UNION ALL SELECT 'N_REASON', 'N04', '너무 김', 4
            UNION ALL SELECT 'N_REASON', 'N05', '너무 짧음', 5
        ) AS seed
        JOIN `common_code_groups` AS code_group
          ON code_group.`group_code` = seed.`group_code`
        LEFT JOIN `common_codes` AS existing
          ON existing.`group_id` = code_group.`id`
         AND existing.`detail_code` = seed.`detail_code`
        WHERE existing.`id` IS NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE codes
        FROM `common_codes` AS codes
        JOIN `common_code_groups` AS code_group ON code_group.`id` = codes.`group_id`
        JOIN `_migration_26_common_code_seed` AS seed
          ON seed.`entity_type` = 'CODE'
         AND seed.`group_code` = code_group.`group_code`
         AND seed.`detail_code` = codes.`detail_code`;

        DELETE code_group
        FROM `common_code_groups` AS code_group
        JOIN `_migration_26_common_code_seed` AS seed
          ON seed.`entity_type` = 'GROUP'
         AND seed.`group_code` = code_group.`group_code`
        WHERE NOT EXISTS (
            SELECT 1 FROM `common_codes` AS codes WHERE codes.`group_id` = code_group.`id`
        );

        DROP TABLE IF EXISTS `_migration_26_common_code_seed`;"""


MODELS_STATE = (
    "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"
    "qQ=="
)
