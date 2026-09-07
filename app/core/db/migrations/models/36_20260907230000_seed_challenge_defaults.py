from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `_migration_36_challenge_default_seed` (
            `entity_type` VARCHAR(20) NOT NULL,
            `key1` VARCHAR(100) NOT NULL,
            `key2` VARCHAR(100) NOT NULL DEFAULT '',
            PRIMARY KEY (`entity_type`, `key1`, `key2`)
        ) CHARACTER SET utf8mb4;

        INSERT IGNORE INTO `_migration_36_challenge_default_seed` (`entity_type`, `key1`, `key2`)
        SELECT 'GROUP', seed.`group_code`, ''
        FROM (
            SELECT 'P_REASON' AS `group_code`
            UNION ALL SELECT 'N_REASON'
            UNION ALL SELECT 'CHL_TYPE'
            UNION ALL SELECT 'CHL_PERIOD'
            UNION ALL SELECT 'CHK_TYPE'
            UNION ALL SELECT 'CHK_FREQ'
        ) AS seed
        LEFT JOIN `common_code_groups` AS existing ON existing.`group_code` = seed.`group_code`
        WHERE existing.`id` IS NULL;

        INSERT INTO `common_code_groups`
            (`category`, `group_code`, `group_name`, `description`, `is_active`)
        VALUES
            ('CHAT', 'P_REASON', '챗봇평가긍정이유', '챗봇 평가하기 긍정 이유', 1),
            ('CHAT', 'N_REASON', '챗봇평가부정이유', '챗봇 평가하기 부정 이유', 1),
            ('CHL', 'CHL_TYPE', '챌린지유형', '공식 건강 챌린지 유형', 1),
            ('CHL', 'CHL_PERIOD', '챌린지기간', '공식 챌린지 진행 기간', 1),
            ('CHL', 'CHK_TYPE', '인증방식', '챌린지 인증 승인 방식', 1),
            ('CHL', 'CHK_FREQ', '인증빈도', '챌린지 목표 인증 빈도', 1)
        ON DUPLICATE KEY UPDATE
            `category` = VALUES(`category`),
            `group_name` = VALUES(`group_name`),
            `description` = VALUES(`description`),
            `is_active` = VALUES(`is_active`);

        INSERT IGNORE INTO `_migration_36_challenge_default_seed` (`entity_type`, `key1`, `key2`)
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
            UNION ALL SELECT 'CHL_TYPE', 'T01'
            UNION ALL SELECT 'CHL_TYPE', 'T02'
            UNION ALL SELECT 'CHL_TYPE', 'T03'
            UNION ALL SELECT 'CHL_PERIOD', 'D7'
            UNION ALL SELECT 'CHL_PERIOD', 'D14'
            UNION ALL SELECT 'CHL_PERIOD', 'D30'
            UNION ALL SELECT 'CHK_TYPE', 'SELF'
            UNION ALL SELECT 'CHK_TYPE', 'MANUAL'
            UNION ALL SELECT 'CHK_FREQ', 'DAILY'
            UNION ALL SELECT 'CHK_FREQ', 'WEEKLY_3'
            UNION ALL SELECT 'CHK_FREQ', 'TOTAL_10'
        ) AS seed
        JOIN `common_code_groups` AS code_group ON code_group.`group_code` = seed.`group_code`
        LEFT JOIN `common_codes` AS existing
          ON existing.`group_id` = code_group.`id` AND existing.`detail_code` = seed.`detail_code`
        WHERE existing.`id` IS NULL;

        INSERT INTO `common_codes`
            (`group_id`, `detail_code`, `detail_name`, `description`, `sort_order`, `is_active`)
        SELECT code_group.`id`, seed.`detail_code`, seed.`detail_name`, seed.`description`, seed.`sort_order`, 1
        FROM (
            SELECT 'P_REASON' AS `group_code`, 'P01' AS `detail_code`, '최신' AS `detail_name`, NULL AS `description`, 0 AS `sort_order`
            UNION ALL SELECT 'P_REASON', 'P02', '정확함', NULL, 1
            UNION ALL SELECT 'P_REASON', 'P03', '도움이 됨', NULL, 2
            UNION ALL SELECT 'P_REASON', 'P04', '지침을 따름', NULL, 3
            UNION ALL SELECT 'P_REASON', 'P05', '우수한 출처', NULL, 4
            UNION ALL SELECT 'N_REASON', 'N01', '오래된 정보', NULL, 1
            UNION ALL SELECT 'N_REASON', 'N02', '부정확함', NULL, 2
            UNION ALL SELECT 'N_REASON', 'N03', '잘못된 출처', NULL, 3
            UNION ALL SELECT 'N_REASON', 'N04', '너무 김', NULL, 4
            UNION ALL SELECT 'CHL_TYPE', 'T01', '걷기', '일일 걸음 또는 걷기 실천', 0
            UNION ALL SELECT 'CHL_TYPE', 'T02', '스트레칭', '일일 스트레칭 실천', 1
            UNION ALL SELECT 'CHL_TYPE', 'T03', '물마시기', '일일 수분 섭취 실천', 2
            UNION ALL SELECT 'CHL_PERIOD', 'D7', '7일', '7일 챌린지', 0
            UNION ALL SELECT 'CHL_PERIOD', 'D14', '14일', '14일 챌린지', 1
            UNION ALL SELECT 'CHL_PERIOD', 'D30', '30일', '30일 챌린지', 2
            UNION ALL SELECT 'CHK_TYPE', 'SELF', '직접인증', '사용자 제출 즉시 승인', 0
            UNION ALL SELECT 'CHK_TYPE', 'MANUAL', '관리자 검토', '관리자가 인증을 검토해 승인', 1
            UNION ALL SELECT 'CHK_FREQ', 'DAILY', '매일', '챌린지 기간 동안 매일 인증', 0
            UNION ALL SELECT 'CHK_FREQ', 'WEEKLY_3', '주3회', '완전한 7일 구간마다 3회 인증', 1
            UNION ALL SELECT 'CHK_FREQ', 'TOTAL_10', '10회', '전체 기간 동안 총 10회 인증', 2
        ) AS seed
        JOIN `common_code_groups` AS code_group ON code_group.`group_code` = seed.`group_code`
        ON DUPLICATE KEY UPDATE
            `detail_name` = VALUES(`detail_name`),
            `description` = VALUES(`description`),
            `sort_order` = VALUES(`sort_order`),
            `is_active` = VALUES(`is_active`);

        INSERT IGNORE INTO `_migration_36_challenge_default_seed` (`entity_type`, `key1`, `key2`)
        SELECT 'BADGE', seed.`name`, ''
        FROM (
            SELECT '물마시기 배지' AS `name`
            UNION ALL SELECT '스트레칭 배지'
        ) AS seed
        LEFT JOIN `badges` AS existing ON existing.`name` = seed.`name`
        WHERE existing.`id` IS NULL;

        INSERT INTO `badges` (`name`, `description`, `image_path`, `is_active`)
        VALUES
            ('물마시기 배지', '물마시기 배지입니다.', 'media/badges/water-badge.png', 1),
            ('스트레칭 배지', '스트레칭 배지입니다.', 'media/badges/stretching-badge.png', 1)
        ON DUPLICATE KEY UPDATE
            `description` = VALUES(`description`),
            `image_path` = VALUES(`image_path`),
            `is_active` = VALUES(`is_active`);

        INSERT IGNORE INTO `_migration_36_challenge_default_seed` (`entity_type`, `key1`, `key2`)
        SELECT 'CHALLENGE', '스트레칭 챌린지', ''
        WHERE NOT EXISTS (
            SELECT 1 FROM `challenges` WHERE `name` = '스트레칭 챌린지'
        );

        INSERT INTO `challenges` (
            `name`, `challenge_type_id`, `phrase`, `description`,
            `recruit_start_at`, `recruit_end_at`, `challenge_period_id`,
            `check_type_id`, `check_frequency_id`, `reward_badge_id`,
            `is_displayed`, `is_deleted`, `deleted_at`
        )
        SELECT
            '스트레칭 챌린지',
            challenge_type.`id`,
            '하루 총 5분 스트레칭',
            '하루 총 5분 스트레칭을 해주세요.',
            '2026-09-07 22:11:00',
            '2026-09-30 22:11:00',
            challenge_period.`id`,
            check_type.`id`,
            check_frequency.`id`,
            reward_badge.`id`,
            1,
            0,
            NULL
        FROM `common_codes` AS challenge_type
        JOIN `common_code_groups` AS challenge_type_group
          ON challenge_type_group.`id` = challenge_type.`group_id`
         AND challenge_type_group.`group_code` = 'CHL_TYPE'
        JOIN `common_codes` AS challenge_period ON challenge_period.`detail_code` = 'D7'
        JOIN `common_code_groups` AS challenge_period_group
          ON challenge_period_group.`id` = challenge_period.`group_id`
         AND challenge_period_group.`group_code` = 'CHL_PERIOD'
        JOIN `common_codes` AS check_type ON check_type.`detail_code` = 'SELF'
        JOIN `common_code_groups` AS check_type_group
          ON check_type_group.`id` = check_type.`group_id`
         AND check_type_group.`group_code` = 'CHK_TYPE'
        JOIN `common_codes` AS check_frequency ON check_frequency.`detail_code` = 'DAILY'
        JOIN `common_code_groups` AS check_frequency_group
          ON check_frequency_group.`id` = check_frequency.`group_id`
         AND check_frequency_group.`group_code` = 'CHK_FREQ'
        JOIN `badges` AS reward_badge ON reward_badge.`name` = '스트레칭 배지'
        WHERE challenge_type.`detail_code` = 'T02'
          AND NOT EXISTS (
              SELECT 1 FROM `challenges` WHERE `name` = '스트레칭 챌린지'
          );

        UPDATE `challenges` AS challenge_row
        JOIN `common_codes` AS challenge_type ON challenge_type.`detail_code` = 'T02'
        JOIN `common_code_groups` AS challenge_type_group
          ON challenge_type_group.`id` = challenge_type.`group_id`
         AND challenge_type_group.`group_code` = 'CHL_TYPE'
        JOIN `common_codes` AS challenge_period ON challenge_period.`detail_code` = 'D7'
        JOIN `common_code_groups` AS challenge_period_group
          ON challenge_period_group.`id` = challenge_period.`group_id`
         AND challenge_period_group.`group_code` = 'CHL_PERIOD'
        JOIN `common_codes` AS check_type ON check_type.`detail_code` = 'SELF'
        JOIN `common_code_groups` AS check_type_group
          ON check_type_group.`id` = check_type.`group_id`
         AND check_type_group.`group_code` = 'CHK_TYPE'
        JOIN `common_codes` AS check_frequency ON check_frequency.`detail_code` = 'DAILY'
        JOIN `common_code_groups` AS check_frequency_group
          ON check_frequency_group.`id` = check_frequency.`group_id`
         AND check_frequency_group.`group_code` = 'CHK_FREQ'
        JOIN `badges` AS reward_badge ON reward_badge.`name` = '스트레칭 배지'
        SET
            challenge_row.`challenge_type_id` = challenge_type.`id`,
            challenge_row.`phrase` = '하루 총 5분 스트레칭',
            challenge_row.`description` = '하루 총 5분 스트레칭을 해주세요.',
            challenge_row.`recruit_start_at` = '2026-09-07 22:11:00',
            challenge_row.`recruit_end_at` = '2026-09-30 22:11:00',
            challenge_row.`challenge_period_id` = challenge_period.`id`,
            challenge_row.`check_type_id` = check_type.`id`,
            challenge_row.`check_frequency_id` = check_frequency.`id`,
            challenge_row.`reward_badge_id` = reward_badge.`id`,
            challenge_row.`is_displayed` = 1,
            challenge_row.`is_deleted` = 0,
            challenge_row.`deleted_at` = NULL
        WHERE challenge_row.`name` = '스트레칭 챌린지';
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE challenge_row
        FROM `challenges` AS challenge_row
        JOIN `_migration_36_challenge_default_seed` AS seed
          ON seed.`entity_type` = 'CHALLENGE' AND seed.`key1` = challenge_row.`name`
        WHERE NOT EXISTS (
            SELECT 1 FROM `user_challenges` WHERE `challenge_id` = challenge_row.`id`
        );

        DELETE badge
        FROM `badges` AS badge
        JOIN `_migration_36_challenge_default_seed` AS seed
          ON seed.`entity_type` = 'BADGE' AND seed.`key1` = badge.`name`
        WHERE NOT EXISTS (
            SELECT 1 FROM `challenges` WHERE `reward_badge_id` = badge.`id`
        )
          AND NOT EXISTS (
              SELECT 1 FROM `user_badges` WHERE `badge_id` = badge.`id`
          );

        DELETE code
        FROM `common_codes` AS code
        JOIN `common_code_groups` AS code_group ON code_group.`id` = code.`group_id`
        JOIN `_migration_36_challenge_default_seed` AS seed
          ON seed.`entity_type` = 'CODE'
         AND seed.`key1` = code_group.`group_code`
         AND seed.`key2` = code.`detail_code`
        WHERE NOT EXISTS (
            SELECT 1
            FROM `challenges`
            WHERE `challenge_type_id` = code.`id`
               OR `challenge_period_id` = code.`id`
               OR `check_type_id` = code.`id`
               OR `check_frequency_id` = code.`id`
        );

        DELETE code_group
        FROM `common_code_groups` AS code_group
        JOIN `_migration_36_challenge_default_seed` AS seed
          ON seed.`entity_type` = 'GROUP' AND seed.`key1` = code_group.`group_code`
        WHERE NOT EXISTS (
            SELECT 1 FROM `common_codes` WHERE `group_id` = code_group.`id`
        );

        DROP TABLE IF EXISTS `_migration_36_challenge_default_seed`;
        """


MODELS_STATE = (
    "eJztfW1z4jjW9l+h+DRblWcWCCQk3wi4u9khkAXSM30PUy5jO4m3wWaN6ZnsXXv/9keSX2"
    "XJjmVsLIOquoOxfWR8Heno6Lzpf5tbS9M3+58Hum2ob837xv82TWWrg4PYlatGU9ntwvPw"
    "hKOsN+hWJbxnvXdsRXXA2Rdls9fBKU3fq7axcwzLBGfNw2YDT1oquNEwX8NTB9P490GXHe"
    "tVd950G1z4/Q9w2jA1/S9973/dfZdfDH2jYT/V0OCz0XnZed+hc2PT+YRuhE9by6q1OWzN"
    "8Obdu/NmmcHdhunAs6+6qduKo8PmHfsAfz78dd57+m/k/tLwFvcnRmg0/UU5bJzI62bEQL"
    "VMiB/4NXv0gq/wKf+v0+7edvvXN90+uAX9kuDM7X/d1wvf3SVECEyXzf+i64qjuHcgGEPc"
    "fuj2Hv4kArzhm2LT0YuQxCAEPzwOoQ9YGob+iRDEsOMUhOJW+Uve6OarAzt4p9dLwezrYD"
    "78Mpj/BO76G3wbC3Rmt49PvUsd9xoENgQSDg0GEL3b6wlgu9XKACC4KxFAdA0HEDzR0d0x"
    "iIP4j8VsSgcxQhID8tkEL/i7ZqjOVWNj7J0/+IQ1BUX41vBHb/f7f2+i4P30OPgtjutwMn"
    "tAKFh759VGraAGHgDGUGS+fI8Mfnhirajf/1RsTSauWB0r6V7y0razjZ9RTOUVYQXfGL6f"
    "N4k875FAJyYXdD51ajn4d5Q5sfwOxp7iHPZNcP73pmrrsJ/IitP8g2nKeTBez2jWuet0rq"
    "9vO63rm36ve3vb67eC6Ye8lDYPPYw/w6kI67Qfz036VjE2LEI1IChGrJaOcvmz0puyfwP9"
    "eKfs939aNqXDJoNJIa3nbFUKsJ60oOIpmYctwnQMfpViqjqBbUh9OkibT9J0NJ5+bhK4+l"
    "fuG97ByhwMl+Ov0n3D/VyZi+cFvCaN7hvB4cr8dbz8MpoPfp3eN4LDZg4O3WXgz10id+7i"
    "vEGfDD3dv7+e3bsUZWwHgKBguNT/SpjcAoJcIHqClQ/Nayn9tkzXvLbv3pXJbPrZvz2uju"
    "GArg3beZPBVEdBdQTO0lHFqWLQwtOOsdV/9q/XCeTRYCnFIAI/X3M1vTwiNaSutgc2HwcT"
    "IDjh35X5SXK/uZ95RONNhrF9kziyb4hFVqjYUrsh7E8Jay2MMq0rwgNOBSd4B21mbt49hq"
    "cJgfGjtFgOHp8wSQB7LbzSwaSAf5ZgRNAImh4b8Gvjf2ZTKb5UC+5b/k8T/ibl4Fiyaf0p"
    "K1pE7fTP+sBgjD3stJyMxSkLYOzp5czZ8BX9eIYFe0TnsRzj5V1+M/aOZRs6RTN98Fr49M"
    "tc3ygO3YIXWZRPUYtfUIPvfI7n//p92T8b8j8i8hRbl/WdsQevdiQsQ9CU5LZUY0BerM0G"
    "9MHDTv5h7A3nSEw+odaed19hWzVGxVJt+V/W+kg0Zqr9D2tdYxjUN8WR9/oeWviPHS2gqY"
    "XbUo0BUeDrgulxrWivRYjVB9jOSfForg5r9bq1Oqh3aqvhfqwOit66g19aigr+3ih34O/t"
    "XasxHmVTU7P2pg1UZXV5p9iOoRo7hFABMA79lk8Npape98Hfnq6Wjp6yUeztkVgNYBs1Hn"
    "67w/5N3h/WwROOxOMJtLeINFdjaKBK+GpbB1MrYOJ6CBrLNn9VZkxIx2Sra4aKXlXWrP2x"
    "8voxaG0EGqtxV4nAAhYKxcEC1gh1hmV/2O02+lY3HdnWfxj6n+BjZ9nHqsSLoNk5anWOGj"
    "0PnMwDaE83j4UITuEhTFOv0ZpBxOQuj6CpOw54XgqCM1NfWuBPRhwj7dVHaucIH8AtEgmx"
    "BITZIj2wQKYZTkqONPADGryOIH/X0Q+NBh2IIAReghBiTMrl7cWbqNjN2Bwv5OlsOf70TX"
    "6URuPhYDmeTe8btLMrMzy7GH6RRs/QmUGei973+Xk8wm5CJ/K4PjpZ/JqdZLdmh/BqmmCG"
    "/6FsDhQf3INlbXTFTHAQR+li7FsDQq7nLepQmM0mmAH8YRz3YT4/Pkjzn9oIXXCT4WDjRX"
    "iUzszzQPEowdmRdXqJEH08x3DCwpNNM4RjBwebRPqTZevGq/mL/k5MMMnqIJ8oJ+mB4LSt"
    "/BkoNtEOBNfw+kZ3Bc9wsBgOwDzy3+qiVwM9O0HzjOrhHyid0SUAP/kSQm8sUG809v7SIj"
    "S+MKodSU2cUANh7ZGVqCAhTqGhIjfUeBMC6kSo1TddO2xYVWl6AwLmJJhfD4aWH+OAWgBM"
    "AOzo9nYvK0Bj1mlz4QcAx6kFwDjAUXxyrA0p5LWMTKvJetB/7dQFoSdT4BuC2TEXWxOaEK"
    "ytmLVbyzahhTLiJ/RxjyUAJLI2pYkk9pZp1mm2+vetFvjXLI3DGBupLAxtkf2/0dgGOYbx"
    "YXMw1bdjuJDYQCU8aF/XkAf6D/3YsZDSRDV8uKshH9a6BkE5hg8pTVTCh06nhnzgww58Pk"
    "ajo/LxP7IY+5EDJduLy+ZGOdbioyzAA21rmE1adRx04Sq1OE5wS7mBBTZYs7qxA7RiBut3"
    "2f0hIrqAGyuxKHEgShzwCqwocSBKHPDRvUspcYAmy5yd26c9YddeLAefPlE69mD0OAadE3"
    "2ATgzvAh04uJkR6SxiJFmI0Iqi2daPXKbCGKkwEVZsIhRxXuca5yUqB5wBX8nUy9iqj9mE"
    "k9BALnNOBYzlIaqPWHkTDGCO8AusDdwhntVmk9CvMPvNQlo2ps+TSVq4H2Vqgs0dmy9bO3"
    "ypwvzjHKPMYHhhjSedl2GedbvTBX/77R5Mre52G6vD+k7t++nr4BjlXF+r4Ljfg8nYaxXl"
    "tatrbXXQeuiUorXQvShLG+Zng4+OpqF7u+6pbFpytmx3v2cXUCoga5mA4upWAVC6L22Epk"
    "aDrtDUdr+f1hUqVetBXPr9HupS7b7bVUvHze9iQWGF42t0ZC6jUPOuVnfIqupybmZ0FED5"
    "h24bL55HtSg0v0baPDWyCMz1tYYKotzeoknmDvVMtQ+Q1dpK63Qj29puAUxqAdWqUEvDbM"
    "WqCsWzBadYtX3dPvkUHAz2M0AxdYifRJGJoCjD4iC7wrD8DFu76G55DoBW10OjlTsU87us"
    "GfvdRnk/Es6R2wpZmGIOnnFqcPutLoIQLnDubt1qU34HPuECp8ysOmx9mRRaEVl/fhBhcb"
    "q0ut/DBQwWVBGxiJ5TUEWT3tGCFXruXsdHEMaHJR7ofCmlrEN5HFK0GyhKtD40pWgtpZvL"
    "P5jFEdtL9sP2CDfsfuvs5DdrT/E+pEAfJaq6nsbicfmEwG5DfFWEr9p/gWxo99U8KJcTzg"
    "Ex8wtR4UAnih6MpuKEfirO2rUOvmiddZ9J4By5nVoMVHoo5ge91yfipffiy17Vkxuc9V4v"
    "UEvWTZUZ8Dhx1cDDIqI9ALN2AwuKajfweN1tqw0aR9Z6F15WkYhX+32XLJ8EzybC02Q4XY"
    "i/2NZWZg5opJBWzRmPAWsVChq1o7dcbkAGKD2k37jqOH8y/iyDNJpxVTO6joe8cJdJGZlw"
    "Lg5/rgM5SmR+ohX8YntCsnMtb+hHQgNVK4C8OYW5iDEhDBEEp0uLMTlj1mZOQKKPFCyYZQ"
    "6G83w8XFZVuwruWjLQfhiq3qTY2CJXr9IsbGgbFQXdWIJ97XdsmxbEI9cWKwONHdzyB2GA"
    "i9+vAj68wpKv52R44zDc7SrFkBbwgKr/fxxWH6WvehGA0kLGy29eggg4Wplfvn0eS1Ppvu"
    "EdrMzRWFreN+DflTkZfwIj/RsskRocrkx/9KMiq5Ev8MpI/jQZfIan3aOVOVt+keb3DfSR"
    "Z1XRbmdJlGgn50m040sKR/+LyTTn31/PTJNSVse4KCOwTJQ/BF3NSmoWZmU7y2Xt5cWoc7"
    "1kFdlBR2UHRbQx9kwDkrhmkq7iNIOYKnzk8q+2uxxexTMNyH7FWlM4GgapWj9026upKO+t"
    "g60eG1s299r8DJtcoBZ5llQZdg7c6vs9WIUWAw/cQPDRbbCO4JS9pvfHaMKiPjKEP1jVRz"
    "dHPdXWJ5H6JIEndKOYpg79c2cXQMPhfHKVso53DCcpNz5h0ecT1HPV184U1tJOiWtpk4Et"
    "ysZQEqpnJGS8+wTVbmCfe+VceGRQ/eqPuLVEmgSmzXixkeHs8WkiLWGxkeAQnB1Mh9Jkgs"
    "76h3msQAUXG9EM5dW09gZTb8aIatqjy4iUONivepKFNCFCIiQROEZsakDhBMDIcI1Ptx4k"
    "WtVilGnWAy7xTYETWgNiUEX3RKWGyCcqThTKeqX/Fxfnh9YfsrdJPLOFg0peLyhPopJGVp"
    "OW+WLYW7fzwTptLBKTSlxL2XnTzSA6b7qJkhNeogKbz5oeoxVm14rNrkDJtfPZz3FK4Rjh"
    "zDESmXkRp5i1nMQGLkfZcd97v7ES/NcfryETG6t2Lmk+zuZTVMzSO1iZk+fp8Mt9A32sTO"
    "mr5F73DlbmgzSCvfK+4R3kWVWmTer+VHSbOBPdEhq8+5K+uY9RfpHUYjKqeDKK2W8ZGUpS"
    "C4ZW7dS1tjvoK8unKuK0gplVM1PE0JynqihiaPjnY6YRysdGK+dkUEpLmxAbbh+94XYsAi"
    "mSHHBEzAeWjlAfWLGR7Nl5j4Riptr/sNY8i92PCsdFI6aKDJWqcdcQUVIfgbMH71JIXUFn"
    "4bZUXzyUjWJvj63hC9uoLwShCe5IHB6DhmosPaIOWWt/rOQIIRmBxs4DFtNyioNlamWyif"
    "MES5lBp5+szcb683n31dgb8IFE2Cl+w1Va4OkLulU+7OQf8OaTxZ6iiFP0yMAj4n7zl7hA"
    "FRaRp5VFnuKcyerswqmO9HBVN5ozurjw/opjlLwXLk515Pa33Bl6MGtOMfvevln7neEoTM"
    "WMojS1jDcRVYmE6VmYnouQSLzwUZiehemZk8XJVRmmZ5GXKSyOwsLGkZXAc1tQzAOhQyPZ"
    "LhB1nRRdYsoXvGBQb3eWo5vqOyrejWwCrhzCUuk/LjoVTWPV/9oZYEoWqavV1nKvX9LgP5"
    "+lZy/PDw/zdC/cN9zPlfk0nw2lxcLdxjw4hoWkBqNv8qfZXJ5LX8fSr7CgFH4mTDgM8w1X"
    "5qfBGOUaup/FpR+2b7Jk0yYv0OElfAUZH7FU9iaNIIK0pknKZWyCbpi7A9AOFNN40Wkl+P"
    "+xmE0TcCUoY7A+m+B1f9cM1blqbIy98wefIKdgCl8eW8H5UP70OPgtjvJwMnuIL81gAw9E"
    "VrN9UJ2DDRa/4C74BgygU4kLwJ2r1XMpsEO9AqkbLLIDIxJSg+jDcPcTZlCpxLU0lpaC7c"
    "62tjsHbrHoxy5kBZakFKgGPVZ907dKHlRJynoKglLqc7zq3jxE0bjTZrEYoZjBMsxgyo9X"
    "72EoDVfTvQVMzOyuq8ZW2dCBT2oibn932/jZa6tu6I+k4fhxMPmpd+XmRQMeGK5h0edCl+"
    "jLIR4BQAeTZaek5AbqleZfWMUEZNx19w4GqwRHfZNtulc/rcMmNyK6rG7blo22EmWZznAq"
    "oSBwmEnPVc+snSsTetvfc7AxSieYWDETI7Z0RjbilIKRIutUhP6I0B8xQkWS/0Uwk4cy/J"
    "dSok4EzRWNrgiaKyBoLkkeFIAe284Q/MQ7xTH8aGOIhbRsTJ8nk2wRiNWkKPKDbqnRZHje"
    "NyWojEgMT44toySkl5xylhYvtgOc1k0H4gn3THPrlKIrG8V83W8N502Gvw31UHQ+siQSEW"
    "Yiwix7hFlQYr5JgN+kV6JfPD9J84U0gqfD42Y2NsWstZmMtSm22rip1g30RsOG5qJJ9jsS"
    "hCJiKYvjkSqoqN0/IS4hgb6efvTiKzKjmUpG3xhQxanqiWUpnhwXmByRHgSh8I5xE5R0nl"
    "1VRCUVH5VEUZ4ZcKVTC0EQ9FjlRXfe5SN14HgjVe/1/SRNR25WhXsA9N/BJwlovuBvuIM3"
    "1IXD45X5MJkNf4EnvYOV+XUwGY8GcHdv2c+tIE7l0qGzlN5uJ9febhPFtz0WgAXlHgCv+r"
    "v/ZY7go5MLfTqLPi0Cd4qUSJz5r/jqv7VzYO0PO6DS6Fq+SKw4sfBHVu2PFOEfIvxDhH/w"
    "PEJ5iBi4VKd2pe5Zjn3cH/lnmQrEVFgRhiOIE0vCFFcLhmdZLarAVOm39wbMR977cFxl9e"
    "FH6xkVXS0GfxJ8gmo4bpFhy9ZgKVnC3R8jQU77MDrEc+KHWyW4J2KVcL3ggMN6Y6iwpKmy"
    "1x2/cIW3jSx8DOBPULrmh6460DbwdjC/y6J+baXBAS6HEFQE0hmto3gTldtGB8uxNF3Ki8"
    "FXaSR/GkuT0X2DcnJlPj0/TMZDeT74LA+/PE9/AbfFzuSyfWbZzL6dvJt9m9jO3vdHe0B/"
    "B5jk5VVCUxVvDzkczCVZehovZiPJ5xh5bmU+SqPxENmm7xvhMawDBO4djL6Oh5JH6H5ZmZ"
    "9mk8nsV/n5Sf46XoyX943YiVwM7mdhcD+Zwf0kBr/4Mu0Y1gaNVMzU0XjweTpbjBf3jeAQ"
    "xunMP0vzbzBIBx2szNF4AXH5LMlwfQlvjn6PMh2c+LaIch6dyMXCLEWD28k1g9tEyWD6/J"
    "fZ6UylFjbzYOtVD5gcjmcKqcA1qMweU8QYcKWQ1hLXUgqIk3ovA7JU4lpiW45H34UnZa5M"
    "hZWT6ZEnRN0xnLwESLClYlQCzfiKynA2THjG6WqJaJnS1LJfFdP4T2DWYgQ2Ti7wjeF7sC"
    "ll8Zb6XwmmFpyqJmimecKk35aYE4wInQkcYZPZ9LN/ezyehgrtDtYPAyu4NS0nMNGYRSeu"
    "V4prYeWZPDDAMkk393kEa4SyJp31FEPf2BobxTZgdCNQN1nLXdHIRaGrmNk9+4AnCWvmnS"
    "5stIs4nDONw4l4k/JFb2C09ZoLT1zuIeanY4abTi8gT4E8sq8rK9oEqQA6BeiYV50VbCp5"
    "zebaaiPByGCDI2PBiLII/AGfNRqM2rs+rn2yxappHAlnTUtzxKEkpCIGo5/cRKkh4wWsHA"
    "8kjFEcBI3VFkhSd8qAZDzS53g0iQ23awsoXTtKADU57LPMkLZoqCMllC0WCZkcwkZEXxYd"
    "uYYesAcP8MTVXgf3wMrkpkUNWttt3kEL/k9yY8oiEWw2JN87QRkaUZ6makXiqpEcgRbhFg"
    "F0slEPp6qlQa8c71Nk6BBwJluacaqaacKFWZ1sK8ll93H4lU9bdfjj80Ka3zfg35U5WCzG"
    "i+VgurxvBIcrc/FtsZQe7xvuZzNHz80S4Zgc4EjENyZWRkp2PiXXROK2jsTJXU/1K/vlVT"
    "Nokr2aUvBgOZcGj+hccBjuGokXB8P3jeSgx9vWwTku6BpvoeJQTz+6evQQRlqPHqIB1tHQ"
    "anDeu2cwHcnu+ZAuPLcyP0tTaT6YyJPxJ6BKf5tI9w3i1MoEchycGrphwZEvblGM5TcZ6O"
    "FPs+nCq48RObEyZ89LefZJXgxnT1LkPurpPP2m087is2snu+za51bQhG2QX1xVEybHNpVa"
    "6MJhdKttvPjmo+MGTEJTJxw209kSSKJ/Po/n1KqY0cv3jeg3IG6JcfVVmo8/jdHA8I6KmC"
    "TbnSw87CSzsEPb5WxjqM6R3KM0c2LODZ6ewIw2eJhICbwLb3C5F35fmdOZPJxNP4HvS3gx"
    "+BJOpEC0DeSn+Xg2Hy+/Rebg6OlgOl7MnudDSZZ+G06eUb1U+nkoceFW3JFuFTuRa0LM0k"
    "c6yX2kQ/SRyqpRnqXMFMUoi8e08mKUZ4lq5bUoq0a1+FKUXBVOrhre4usmi0qfZcoDUaWw"
    "0IzLg+0udmhlRhL9CDGqeoUwFReqLrZm5T5W1X9tsdXcxTBThJSfZ0i5KO3IPx+zjdBIGB"
    "B7cgBJXLMwhhOHUOeLnD46YPpyItTxKLUcMerUBgToDOVKY3GFx4YCg+YWYWv8CZLMwcCk"
    "rPw4PJ0IuywG0DrW4ozjmTBUE7boJIRwAUiyZk/wi2VizgTbHqeQJYaoFXtfUDnhCBK1LC"
    "Z8ojD75LqxVACzhdyXWTM2+hzY/ocVYzGCP4L6sH5N8D/yV5BF+0TvD7vdRjYP4LfD8E50"
    "AbBRh+8Mf5Z92BAPkf04mOCaKEbLr7p21RDFaPMVo12ZMKpbXjw/PU2kRwlGdcdOYLGQ8v"
    "wZBpPEz2AFNf14SHQn/TwfQR6iBK4ogStK4IoSuBfskBUlcEUJ3DpVFhMlcEUJ3NogKkrg"
    "ihK4NZCmogSuKIFbuzxkUQJXlMDleeiLEriiBC6Ho13EK55pvKIogXuyICwuNou+GLCjPu"
    "tc4ZsFRLpdTPimqO58csjjgQjMmCc0IEAXJbW5AjoSUHMM6GQzggEpDKAEQDGjn9yGgJ4x"
    "bryqMGeOwiavaHHjKTHO1LhxLD6wADBBc1LYGncdODOW5OoiQ0VuUSNe1IgXNeLrAihTjf"
    "gPVIECgH0GrS5go/oWNDiNNFxbhJP1nQwoE4Hlx0M8Dpucey3WFtuE1SrTLIXF5hc5Yy1Q"
    "u7XHOHW1xN1mEn7yY0J+SyQ38oPMFi/3sISUFiJhBUoI5LUKSj9ulH2oxSoOJYslvP0Pd/"
    "+IGIHIEKksQ6R+Rc1h7sVXWtlP98J9w/1cmSPJq1zuHTSz8QXzkGepUJxcoJioT2zs5Y3x"
    "nSK5HyxroytmQq8OqWI4rwHZKeV1c3VQ+/01+NvrdsHfm7tuA37R1dVhrfVb2SBO68Wz2Q"
    "RzOz6M4yExz48P0vyndsx1TisYkKsINFfVnwHe2rV6tzooaqsFkW4pAGkVCAX45aUHeLDu"
    "amqent3JEqfYSQ5T7BAxCnGxToCe7mWnkIsKMhVXkHHVpTwxEzilYGTVpYBE8Mt5Br+IYl"
    "388zHbCBWhNSd2DebyBYpQGmbvn28xKMDayifKTMZV4eYr1c0XYJmlqFF0D9aYHCitqhFH"
    "/bPUKj4PikbfJte9cJVm01zDW8o3Zv5vM3wXaGSBtvkfqORNU/9rZ/s2VY8wtEn+Jbs/0C"
    "eAP93rEk1EC34y+oIGdOQZvi69fgeawdYwvZ1zMz4t0MQhafaH+npevocGWuIHDz0jE25z"
    "dVir163VQb1TW41xVrshF/Zc1m17jtqwpxzAoX3rFhq27vrdPIatcqpFRH4wA7wxssqNiT"
    "jM7Q6EWen38sDcywRzLwXmHgmzsYXGv53iMG2TglNVXaKK3pnXL/3wVEttg1PXyKSrqGsN"
    "fOn3cllxy+FCdGZj81OEdPk8Fbn4EEiZVD64pvMb5Y5bj8VZGukgH7ovbdTFNXc8QD50Mn"
    "sthO2uTrY76CHUeiryE/YguzttKPj67d4l854oIktbCTCpyQkNVGv1i491RWu1oCLnOi3v"
    "+FSmyfGYmykJDVTOlOQRWQMOpeUVxAZBAXaygd9O7cZMZgsaXXJkKK4e7941hbuE0ZDZAk"
    "wXEEfVZUdX1TdlAxcFBdgy3XZOzRO1CxXyu3VEYb+BIUbrvqo2XJ2h4V4CbNJbd6uD1ruB"
    "t+Uw1STaQwkXkQJxOxJS6LcIbJ6nVLtDsAqGqeSwWK8D0oNiw96ZGhIbGQwnNSFrxn63Ud"
    "51NKzhdzcMBn6zddU+GGjPdNvxNHf/nG5qXuTsR2bZ8N38Z8k73TYsjcEK7TeBeqongiK/"
    "le1XoGfmeLb7qzMaoyPPY39bXf0evCnbs0Ja1ue92DroOab6nvehQQPZn+xNBchwz/7YKH"
    "XpHo3o657UqxF58GV6NoiJlj+F/4pb/0aRGk5+y3spDo7dm62w1cALKfgDFyg82g2Kjlag"
    "9V3taehUt+eZnwLtUb3Tb6Gu30Wq5Pq6DxcBN/kCqssoppfqd0oupMmb34mm3iMniNq+7u"
    "dwRaUZAsuouUnT3VjstTR67qz0ioJcVFq74Q8SsAZu5zDb1sRMmyksM6ah5+R7SM031/v9"
    "XrjkvmCux1dybE5QjPSEflD68rYZ9X16dq3o9Ij43uqGNhYufaP4WpqRHyEhF9xo95ECAj"
    "HXOuu+65zWkBWSXwacYypQM468etd37b8XLv9EJMI5e6NFJMLl8p6MRKBYZMkZNr3SLK2B"
    "ilNk6ItORYdeEEVtdVHk3QvQdrX2uhfNpW6MRz8Nv0z+Dv7LT9J8PBv9jT8DGY19EWN+Hu"
    "ZFyLlkHUx6h2qr66j9kHXLb08S54wj/ASMnKPRc8C621u0oLyDU+xa70KF6lrNMt5+kT/N"
    "pX/WgGk5R1qMlDdWqZ07NCNqmVjF//gSEXb8MSXuomRiCIW4cmacNG5FREXyHgfGR1Qkpt"
    "ORvGLPHba2W8scZksdrq8emDmAkqYzZ6mRG1sonRtnylxcsfMGW4xm4k401qe+fDmNTped"
    "HzGtNzMnsACoM2FHaashNnbEF40ZeBKPDjuSIVnjYWurqmVlCEWnzTJCRN6DyHvgQd+tLu"
    "/BHTG1js/H05OjwfquJqXeuTU/80ZsZkpz2Cm2Y6jGDoFUAJIsCSSFounOp56uUzxmJ8l5"
    "eLIt6Nhx139JuQ/BTVeZciDkXfT+QnMh3GLgYUw16hmu2o0C3SLfdVNzy3wn5U7gLYVJCa"
    "q13bGnJQQvHaG/yhpaHv3JuZ4ZaSD5oWcWVn6nwmiWXv8ODrsbHi0mV43ksPJ4ryU94Akx"
    "0PHenuL/PvnSI84SN8wPSkq0AAlDPF13+NFRLtCZHY8qx0YCI6oeVa0wDQIoy8MU9DUggg"
    "FcB9omNoliIk52OvdTi2GWKXsPcH82YIaPQnmRCAaTnO0Nv9ig1lVjq2wSxnWcNj60XeKf"
    "vUbKQrPpxlUWXnJ4JA3Hj4PJT72rTiya0s9A6NJKLWEaCltgK0bKQ2ir1kPFrjovd3F78F"
    "qBwccwAwd+6cAIV7V93eY23DUc7zliIGO0nEXF5WKSCIYVwbBnGRApgmEvl/f0oh9xKwRD"
    "pAONnIM4LzL9h+YMUWH2K5yNOVy8p4Q7kDaoI23zlZoxS+NVZlM9rQ8z75wYsucHWMy/eH"
    "syFlWc6Gukzeo8uugYqU0qEqY3LTiddjueOT+fPaxaAzQGbJoROs6BLIZooiecrjIPtVNH"
    "f4+MrElM5l7sdWTfGpXNxBxunLg/rLeG4ykNRzzf1n8Y+p8MRm5/Lc5YNyX22KhzIWuVGv"
    "hDj6jcEvsFF16+BQsx4W/evkoxupPjj6pu07lBJebKVExO5LhbF59HSjEVA2KHutV5clWX"
    "CEn1VUMouhAWT9Vad93rGbv9GRewLxT3KMg1rF9fw02Nn6TpaDz9TBqmCXZgKeqIEVor3w"
    "6w/QzI9xNx78dRt/V/6d7m9mgLXZYBQKPlaxi4Ov663+li2/By0+cDtSpPkRqMlDezVWd9"
    "5/ICcuGmDQPVOnddgiWidIOv1urbneWg8N7vOiV6OmUaIkmr3hcIl313bTjvqC/QaIlZr7"
    "1Ad6/yW0vJtXHQTTfDsLzpJo5KeCk2EUUXd4yjMk7Lm/cA50y/DQecdpdn9J2NOVm4ji6d"
    "38J1dCm8JwOpIwY1gvdpdqUYIQfuonIt3FVlnlPMjkx8Smqh+jxmNCDX19pd3ECiqH2YK9"
    "tWWvVIahauWOGKFa7YXK5Y2lRUAAOoWSdnNBllZUVsks6UMRubLgrgRiVZgyXPLtkzZenT"
    "L3MOYZmO9DCXkOI8xxINkx3maNSXtQM6LWXLTer+ODvLxTs0j6Pky8yO68hrucdhQ9kcx3"
    "FBmP/x2NtfhtuYnMqSsk/5UziuUnzINXT1DH4dzEfSiOrqSU4JPs7Vkwa8b9m8TTRs3sbt"
    "mm7yNeteLDgVB5uGYPujdV7cUikqMTaC3eiR8UOBX1oqzDVuvdzmYUYp+7d4FSRyuZ9ptD"
    "yzR7vphZkJH222zqF/OjJzEVxKtxLilNxZhZOl16WaCUkTMdBjre95/bQRSs5MxBjvtZu+"
    "6q4cLtwZ67IsV0BEjLDyaIgUBvMXDSH8bpclVIXf7VJ4T/jd8tUSPrqIcImqbl0KA+d3zv"
    "Dnlym7FleFPrRcnjP++UKYtGrAivNzZwYFNKH3pafS+HJ2Hs6C/JpnMJSYHJmZPWenLjLL"
    "1VSeFVLWirEFOuUrc8hXVTAzjn0Ol/yZRUacUOyfNm+9bOdwyLIEBzHG0w+cxMHbluYohu"
    "2GvZbdRfwvyzDZXLThOxXjJfboczw+bIn1N3i7Ped4ZrhP9KW6peumK16dmXN6uBx/lai+"
    "6QgbjnVH32Ww+N4l2nvv4tbeUMoQUKcb/zBC3my9ON4dHQ4IVRGG33iqr50zvwqj5I75Hb"
    "27CrelJmViULz3wj1s4YzJwvyQijvGx6ZEuOpxSwtTOkFQbRjtZdLK7x44px4h6iM3RX3k"
    "yhAU9ZETwcpTH/mMy/B+uB/VBctwFa6IwKI4F9tjtNyxParWazr80u5fPMNFwA5lbjrfdZ"
    "sI2LkU3hMBO+cUNlLMpmMiOKSIqZT/eJDzjCsohgvlhBKchdu73J0N4wAXWPo7tiFeUdW/"
    "K0tFP7WLG+vKZ1dHvVI0z2D7WB6CMMqtSh/u2k4rRY/t6Z5Sfx7dB366Vk6YxKttHXauwc"
    "xRjA16EBEpEbnN2Mvg6cYP9LP3lu3Ilq2BxgDF7+TG3ugssf/0H+cVBuBOcFp7Dae5lx7s"
    "1V3N25Jdcx0gbn/mTaG7SnH+R7sDwZLkxK8YGQdpuMjTr7aRzAiYk5ETmNe/kyXRq5Oc59"
    "UhrMMeWKyJ6DEyXjGG+7H1e7wgHf5kJqQxssqTGOlAQ0nT7nSPwTsb4GmIk1XMw7mBQDxR"
    "nuNEVXrgmq7pCxVodnNFUc5+O6voKNgvh027sfnxg102Q7oTbrEZTJ6JajO/W2eeqS1fbU"
    "FtJOeGmGdjz70cW74w3zdp5vvYEoXdik9voPoyqtHhTZSzq8NiJGQSWm0ycyZKVb11P3FV"
    "qGgvaN8HtH9xnbgSX8eze1/oDVQ/dKKisoZDJ8UxE9htjvUeBOaqz36L5zKYsnoWouIF8y"
    "oMB4vhYCQ1U+eZAnhQSfnUUmaVzM4c+lybUDM1TVbVFf5SJFNmZyVdXjOXrI241JAnLZb5"
    "V4An6PROY8It4ebwKmqr20iUV+PRT8Mvk7+D//KTNB/PRn8r0CcEsTlPaGFtLli0yx0FH0"
    "K7/PYkFQms+qaroDvbOng5uLdU/SHGdobTu6hAtpql3/4if5pL/yweXIjMueHq7unlhj18"
    "jGsRnfY03kxXAUx1aQY6Yia/pow0q/K31P69qYKO8GrZ74Qj09XtXN+ncGTWfcma7NWMdo"
    "CsTqAoTfW+tkQewf1skTEdVXvu9flwvEUGFgPkOFXlmzhGXJrhSOAJX1YPMk5VfaemIywc"
    "yMWvJ6lA8+lAFi5P4fI8trsLl6ePl3B5Xgq7hcuzLn4b4VyrAZNSnGvCxyN8PLwOkOp8PE"
    "GqwhEWXCw5ggvzSomO5lLttoONYm+bFGute+EqzUarwFtKLc6JnuByH/5kXdnI+43lUBJQ"
    "fIqwICZWszKsNmjqfzky+A2vr7qdsYylBn5f+K5+X2xexYpkQvuxrcv6ztgHhuIXa7MBut"
    "hhJ/8w9oZzVhbhZJ5yadvF+xJpofm4ZCXewgnLVj5Ko/FwsBzPpk1SKIUX7xvh8cqcPi/n"
    "Y2m6vG/4Ryvz02wymf0qPz/JX8eLMbgUO7EyPz+PR5I8/CINf7lvRL7kMfu0exmsPu1e8j"
    "6AvbjNJ5QAOVmINVCxue1xNp+Op58B19yDlTl5ng6/3DfQx8qUvkrude9gZT5II7jcu294"
    "B3mYUvBemY7hbJhsywFBxWbl7NILN2X2snRqcFeyKbNH6db7vULL4k+GMUJSbTfOiWMp+6"
    "Lt1TddO+SrqxWn5cpWmRnkmlil/Nf+YHdB9WDbOhDjsn1gEzIU0lqOklL20oW99z+WySi1"
    "Q5pT1uveG8rfF7p12JCKT27Bk0nupIidOJ7xFQWj4KGQC9lTtew5p9r27oX7hvu5Mp8Gzw"
    "tpdN9wP1fmcPb4NJGW8FRwCM4OpkNpMkFn/cM8+mbBxfA3yj4YLbnmeWoDPDmqLnK8nWsh"
    "3Mtk5pmWt71MZp5j7Ed23fFcvP6XEeRxmSM04nVgj90giasNCeDSqxCCHXPoMONNpxeQp0"
    "C+tw62qsuvByNH/6YQC7DPt2wyh+imBAjVtSwy6zSbu+wxPXU+6mU/Hr0haE4KW+NODmQO"
    "lCJn8o+xjIrHArCc66r1Q7ffP/vt1RZNyryRIeQsHu5xPKKfUIvPu69+e7VFlK750Ltolj"
    "gy/YcOfwE5UTEEkqEgJwk2VC/5WX5ImAtKUlxYANkHwWFyyKSSU3cVP1wNPdHlM4rAcr8r"
    "IvSqwtCrCE8IoLN5VPAWqs5IXAy/SKNn5BsJDlfmAgVbLVCg1UiajL9Kc3hHcJjkaVn8Mn"
    "56Qm25Byvz02CMGnc/OfC6BIOIYN8HG5FG6IQBkDMD4E5531gKRfb9YzGb0vkZIYmx89kE"
    "wP6uGapz1dgYe+cPnnUVGvfgS2OM84fDT4+D3+IjZTiZPcQ5Aht4iI8b27Zs5vR2nEoErg"
    "hXxJlLIldXZFXDolTC7JRm1Nsd9m/y/rAOfjIz1kktCFtqdmtfsEQ5NgnNb4e/7p3VFhAd"
    "uh8bqYjOVwCIT6DNRaxJ7rptVjiTRidzll6ZZgUCcYpxgcaVZBMD8dqnMDT4NvuwjIgwLF"
    "RnWDC1neUBlFm7jtBUWjqKp8yJXad3o73J33Wm0mc4lUjoCaf6g8MMZpRGQBn2zI3ivFg0"
    "xSmlX0Zoarl8Lj5JAXlYwcTMJitxqlpCWUqnPIvaY0VYzUSRMWHdufrAuoMyLoAkyZ2tEa"
    "EVwaYVB5uK+LArER/GX3xYloCReETCicJG+DEblRo1AvGDdYNN7R/Wukmx7eA3XKUZdtbB"
    "rfK/rPUprDrgMUF0QVhC6Pcm2tRh7ykX6Awak38klheKE3xUWwjcDX4bpE8rLiQsTFVZmA"
    "xN3+4sB23swbigp5DW0d7UzrQYbaesRtvkcjQ63vLEA0Xpq44Gmg3n9w3wZ2VOJo/3DfBn"
    "ZYIXX9434N+VOZgM5uA8+liZ0uNgPLlvoI+VCXS6gTySJpJbvwn72szDrOssvLpOZtU1UV"
    "Olfpnw/3yWnr2wKZxT7oX7hvu5Mp/ms6G0WKAiS+HxypxLy/k3+dfBeIkuYV+TorjwmK3i"
    "8ueL56itv+hubRR3wmUQaRTSWhqFirevhciwTslxSuFST4lkwNQrAuZ0W0KcVhiKODMUgc"
    "nCzsdanFIYiarOSBbVPM6HmdrBRuYQeUvRAhNntRhVvSa1Trt72+1f33SDuSw4kzaF0aYr"
    "x34HqBxobrcUjQCjOp3JtMUPclBdy4cehfIiERSx50XGnru4JBZqXep/JXRHgrAmmKZNYd"
    "JvS2z2IlIlghlsMpt+9m+P508I9+9FaPWizhD/fMykCO4UG2bzQdMrc/pAnLRe+uAl1GA5"
    "Z3C5cbHz4wu+OqYCSzicC4CO8AvXFkNCyh2xS5K7gvG93/lDFeqLbqnRCtJWMTZfddt4MV"
    "QlKRuFvOkqLWpBh7fLPyL3lx+5gEUhoB+AusLBBpM/GnMR5ThDNAL5CvLGsr4fdimxCbFQ"
    "CPAEAzwi/wNRA+/ZH+gSB2oi7EeH7TFvDH2WesrzRTBGZek+fgfPbM0IRoRIqAizKQPhkM"
    "ejHyGvOvBiMf48fX66b7ifeZzr11ksRdfJhqJrskYBrL6mGa/6ninRIkZWz+56082A5k03"
    "EU14KWZ1CycTAswPKs9glPU0Cp2T8UBxHH27c5it+QTdRdryYzoOy0CIkQorWuW+8VA/ZW"
    "RljFSwsmpWCpeFcFkIlwVnI5Qw9iab28q0MD3qWoppKXL1Ks2mtA3uO0UWDLl/dbzWNnoN"
    "6hWvYLKl2sguLIqiVGYlQZ8ExMlrT//+ei46S7GRgMe57TPAGKWpSYzHCeJmNGuvy/8+KK"
    "ZjOEzZUwRhLTEtPtFAf4GGapUJyyhNTWEsoeaRom0N04APpdeUSynVQ1AKVAPzsq2rQCfz"
    "NZaskMbIBJ7R3Zr38k63ZU2hDPpEtYmgq1dUSGGmM9Ny2LQh737RA4MpXHlnivz3br/Q/g"
    "a9zeB3rFPMB4kSECdMsx5wCWUKTtAaIAJ+hfVMWM/44GM2+zYPG4tWMTar3ObSM6Dl3egS"
    "J6/XHFxtJHCl2wpWF11Q6r6CvjX4eDhnql23ANY4kNQRelSIsLvZordJodv8keHC2AaOC9"
    "RirTDH5683xfEz74qBBywbnUe3wbqDE3qWZLjkPRKY0J81tfhenaSjst9YxxYHDKFYgMbq"
    "JfsxLMBpHTobUVA2NMMbxfWScdi2FFj4a4QTk+eYDulW2e3gsxMRnZn60gJ/cuL6GLZfn7"
    "GY28k+gjHJqY72kRe1nMXZLkPvUwke93D7EOTe8i05e09Q4P53wj1P0lI98ZHLwglflRMe"
    "429WEyBGdKT5j694ZYr9z+/0eZIQfNqqMxAeZ/MpKhHoHazMyfN0+OW+gT5WpvRVcq97By"
    "vzQRpB08x9wztoZuvTmJU/rbf6Nv7bRAv/LeFhUr7rZg5rXZROGGE5M8IK6/q5MlYYZc+9"
    "FMNZo8tNLQaOlpNXxxRjEHbrI+3WVceHI4tZ6tLVt6llWroG1rwTbYQJFy3h9gjkElasP6"
    "taf+bR/qJ09dT9aqLrZfLAry2NKdDXv7+eofylRK+JhdCZLoREmBH/fBRhRpwoClS/LyvW"
    "BKkILxKmA2E6OKXAF6YDrkwHdMFaAJR4fjh3EjUrkMSMwRzudhoTDIrUSTXB+LE8mUwwQR"
    "RR0dEDeB9DXlAyTCA8LUwvVZhehGObE8e2WPqf6dK/8jXMparZ1ek4HGuL6UpOxW6mkbHf"
    "bZT3xWG32+hb3XSmB/DW4HOumN9pKk86QaoGpLmk8h7Syiagk22fqFxflLGXdRP+DIQ/2g"
    "3Qk926GfFNeVJ9/S6jCg5npSQ1Vwf1ptUGf3t38G+/rTZWh/Wtoq0OWmt914DnWl3wt6PB"
    "K+ADXFmrKjx1e9fKOF9zoWE5hrNhSuoPCKrWq+JMAFwCTFCUuzzqUikFe6KDh0VlitJxpT"
    "ARmIMP1OXb8MvtreqeysaAmihRmezunmhk5HNIxTeX+/0eGFl9Vb1wLuNTY2xGs6yNrpgJ"
    "UxpGGGP2GlCWxV+6ggAYrGitFuDpneKO31Z8StNuevBK+7qNjrvwek+HAlbrZ5zf0qaq2W"
    "yCMf1hHN/W7vnxQQICF3Eb3GQ4Ca6Bs1yYEiOwBRUMyI0cI/CMF6/n6LcmeK+hkQhkMJpw"
    "232k6vQuuSOQ2cmx1Qi765veQLVOWawnQGF9i8sCIJl7PXiKJsw5X5KkFY+ILy0JTjKbRw"
    "Z+O+fLusz+OHpPP6J2ApiaaduZsyQz0y0kY9Dwyafd8tf9xSRCM9qufFwXYKRooLUmxVxF"
    "3HOVZqEyvbvhHl/h7eXapl5ttHsa3P35nO1N7T7qXe0OlBaaDmZ8Rb8GYkK9a7Ua4xFvsv"
    "wqxbzkcSyrccm7vXrT0voaymW1pbaRkL5xVz7dfKalTJalFMMSUW2Xtm16SoldHjZLh328"
    "9wLnuv71XYCporZyYdrJgmknGdMOGdus2Gv5VbZNg7KU0FVjq2wSoyYjhPGVhEv5s9fCiQ"
    "HXWmhmQmsGuIgH4K+vXa2jj/QNpYeLmfWtevfT69/dpcXfjl7mj6Th+HEwAT346jq2kPd5"
    "1E1ihJKTD0qN2KBqyp0rV7hlw4GyR2QWNhxoW0XyygYg5V2FnD827GzL0YGWnkcyEbRcsW"
    "PdQRircDGk3ql9zsVSCCazZIqT8s4GnsVSiCWzZIqTcs8GjsXSi+LkEkkYHVcMAKBD5VTt"
    "3HEuiFwImYVQlIxf4HkWPS6CzGInSsYx8DwLG2Ot2/nEDU7JF/zIeAhgdbs6kjedFu/Cxw"
    "OUXfxghPVgBNfCyMOTXRxhhDVhBMfCSVU2qnHYytt8tqM4MV8M0V0H892Hi7MtP1zIYTiK"
    "0fLLg1SJxBEPcliNYrQc8yBNGFXNA8OG1ZDziKIYJV/4q8qHihEvyDOLH5yQR9y5ljo+fM"
    "wiByfkEneeJc3uzdqD//Zhn0/eUOn54sLtLfd6D44iu2WaQs4jD7iWQDiI7GZpCjmXPOBa"
    "GlmOst/nXofRyPniAdJA13c3/EukKJTsAomk5pcPfEulKJLsQomk5pgPPEumvaXlFksELV"
    "c8WLfuYCRFZ92vh2QK0WQWS3FS3vnAtWQKwWQWS3FS7vnAs2T6YTgKTABQ5AMQMIqeQ0Al"
    "NcEXX/RuF0V/QW/n+kVtDD6SVKtD63qtvjbmA4kzFjFLroQW+GdQqgjjl0HMIi2hhRowKE"
    "22ccMg582A8Or5FDAKNVeM0Towol7tdbseYzhXwaJ4Mosykph3XnCthkXhZJZaJDH3vOBZ"
    "FbONtfWyUX4YOZ13VHquOOJmuK7VFziR9FrwGGWvg6mF+4Ujji6z3KKR14k3XEsxHFxmOU"
    "YjrxVveJZqpqGoeSUaQcsXV9BS34tUQ7OM2tEzhCg0phWrwyGszGIsTloPhnwgvDhiCLPs"
    "ipPWhCHpEqtyhvjrcTWf3KKR88WY+Fp+yLv6hUGa2wCm8iq5aPzgWuXCEM1t71J5FVxUfv"
    "CsZvmIasiCmFtiRcn55sgoo/2eI7bkFlsRav6ZksVmzxFTcsuuCHUNmJLBTn96phD135Ir"
    "jZVZFissPDay9nqTUhQrdsdVWkmsfXCvDPd+zbZtTXNm6g1H+a6bDUjU2Ol2w9Zfjb2j27"
    "rWCNu8aqjKRoelthqa8t5QTK2x1ZVNA+5z8nOcc8W1St08x23KDsq6wWfIsFom4jltL50z"
    "Ktfln6xJCS6MNzFpB87SUcaI0sqjZhBxBO65ZVxm5NNE1GApxSNSxC5DfOwyhARWjmq+UT"
    "quCjlnFxXnUpsXAYOb6CNzBXNhXgqx2GWIoZhufKLGkc+1qSdZrJVP/LNWxKV0MZ52HaLA"
    "naqmRpmSSVX1C7mWsMui0AE50QFfLEsD+NG2pk2uG4oRFaPflI52yVVC0ScDhP79FWuHOf"
    "ErZVOktbI39vK/nXcWHDGiuoJZdBlg+MKv7/J3VaEYshJlZ4yqZtpUp9297favb7qB+AzO"
    "pElNct+YP8Hb2fIrowUwQsWP5a+QVfFRxRgZUcTojsaRM/OCB2TvqpO9mBMsEceIYUBznv"
    "2QBT5l/8YMX0BznvDlKPXMCGBIdKYD+IahB+4Prwr7ZBKhOs9eyCQD3bp0rFIwpDpPCG+v"
    "4lvgZSnAxaAO4kTVbnhVmTLo1QJi7HwRqvPsfCzjFytjwtD/CLoL7YLRigss8MXILhS9ID"
    "GcATqM5kJxi2efMsBHI71QFG3dMUxrA4BgwA8nulDk1rqjyGApYTngTdnwo5FeKIqRbExG"
    "FSZGeZ5qzE3efDJGMAlaAWeQo8IIJUYnYIwGzTMiGSc9TzBvGVYq0SjenGBq9PnmAsFU36"
    "yNDoNKgSbD3DdJ4vMElMmUqDhyHn8ARneeMHYZYAQtm/tcQMYoBZR73QYqzasMfw2Lzz5O"
    "J9z2OJ574z9MsSRxOoGnF9+uGJt3+cXW/82CJk5VTyx7GaDsJSLZI6Ov7Vc9IRA+Ke7ap6"
    "h2c+lK+yJDKlNknamY32Ugerd7Eu8Hj/bTL3N9E0Tu0gNyybjPOWh5DBo+aQeGJXn7LZTl"
    "r6kw2+wGVcNQYfq/orZ7/g726w5K2EQbPWndPiphgr6sVbQ57+1dq8kyxxHBvViHPgCRKU"
    "fDe48EO3f0c2U6QDo+4LQOg31h4DN4EcMx9MK64zhsW4JNv/MpUBNxOm1IdzBoM4V2R4f4"
    "ByHeKLpbDqQNoig0xPv3pmbsdxsF8ZcSVd4ESGD3oN9iWuecIAil4U0L7uTbu4N/+21YgW"
    "59q0Cp11qj/TYDaRmm6B4jD/kIM/d5S/Ar2QsSUlQcidqMM6XTRhUGWt2fG22U1Q7mL619"
    "3Wqg2awLL96pbkkbWKNLvVHumHhVmPlftXUIUI68OZySq8w5gh3YGGmhnSLb1+2Gm7nu3p"
    "YR/vNNtfPELHOWHU7HwUBkkp7cC8xooCAxQTIzK7kNDhh30kUAFxmWEdUG5yFzcuXIbYmu"
    "753hEMyaoIlLJ3pu5geDrADuVJz2ys0KO86dZHGEcWoO5rb5eLisPo12rv8w9D/n+s6yP0"
    "ilxe78eK3lgmAjIvARUBW83oJWDbSQiqZ2x1dTv1Mun8nqijXMpuI10Vlq59l5cL7Ktqhr"
    "cUrNGdlyWVGOEAl0GXRaf4o5UmV69prhD+Wsyk2kA32sd4paK3WvtZIAOUVJTGZOspKIOl"
    "NolQ8IStIPqcZ4Qk0M7nYU57AXimKFiuJh71hbmbXESIyslo74Ti9LKAO4K7lUS48IZ0Al"
    "DJWtdaAt/1NDwGKUZ5rg3GcIQEaIgJ/PFB2CEdUzwqb4CkJAztoOczlOnOrc63HqpsaMUJ"
    "TmSHz4itiklCt1p2rqSMxQsDSgPt2QbA6Gy/FXt8IobtV0L9w33M+V+TR4Xkij+4b7uTKH"
    "s8enibSEp4LDjM4BbCDfZRjHd4nD+I7Ia7FovTOlDphF7Zn1mJ17mcqA9VLKgPXIMmCemX"
    "RtaUyFwGJk1eIJS653dLjH4N1tHwsEcA3t0H+itaB9vo+25lRfeshYD/fv6rZhDfbOXRdc"
    "0G6gaR7a7xtory94ZX3dz9PPS+HVXgVrV4agjuD+avMxmzSOKGoLodxS+gjybiNwjfTbrU"
    "b7/3oiiEOYiQs0Ex92Wk7G4pQFMLaCieRc+ErEznIYyVFZIrtwBdQcXeEKKNgVwFEICj+5"
    "B3FEC4wciSYkK4681fd75VWX99bBVo/NaQCLEefRbXCB2qsV6IQZr7AMD38/pPoM6dgCFA"
    "boFIZGPFaopqjA7WxKyZJaePvk1AiX03saEUiZvY0+pEweRzngcBl+R4p7U+wGxpWXUex1"
    "xcleV8LgcxaGAYrBhyJ0c61WqW2IxSvj4pUyJYnALPrqltrheIrPIpPKKcoSNfM8WUdKSo"
    "IvWj1Cbb/L3wGvYfOmZW+VjfEfIMfR7ycjs1TFtExDVTaRG4TOVIXOFGNdHtUp1kTVGtRo"
    "/gzUI/h3ZS6en54m0qM0Xd43wuOV+Wk2G9034N882lLxdX5i44HKiASFiaCsaTRSGWFycU"
    "HEgCuFVAArFPyzV/Av2aNbEz76r00wklgtZHEqACGnHG05J/TSAWyVz9GbyVZsaFCrAYDY"
    "RSMzDlquMTwb/cWR7cOmwH4zB63VGBHbeH0TkGCQbHUNKKZo8bkFa1TQ3pHQPAYN1r0CWw"
    "JMe+VFByupAnpRCNUCtVnzrhRxpxfTlUQxv1w2KXdaz2KYChQABuvUuxxRRoq2UZFPi5mq"
    "0LMptir6LcJaVYW1CjHARYoAOpuxCm+halvVePp5Lo3G0nQpTwfQhxc7sTKf5rPR89C/HP"
    "22MhffprPpt8f7hncAzsye50PJuznyJZeVK4vdoJ1sNmgTVgPFlwlZjTABgTC90GxazHjS"
    "aAW0ofjeyztbf9FtW6cJcsva6IqZIMljpDFU14C2LFhZZ8fsRo+H2WyC2TsexjGJPX1+fJ"
    "CAFIgl24oUkIsxGFKUOGYtKKkJEQ/AEA9A12+PDAeo+eLoKhYJkNjTuA4EiFgMs6y8cAMj"
    "0/IrZvUsegnmhqx7kHtfVPDDRAglNwssjEVZ1UqMqJ76ZDtTbnE7Jbe4TcktjnRxdjh9Mg"
    "Go0CKFFim0SKFFCi0ylxaJfD/pmqPvHsqmLQb+qaIVxJ1i2PJ33d1LBzwEVj1S9roj/wAa"
    "Kb0UNPJEhz3VdcN63/+A2/OgNn17r1diJawTZBv772DS+qFv3LuTnyr00Sr00WiPyKo/RW"
    "nqqTzddDPoTjfdRNUJXsI1J2wU5PGbYA1U7TaBwb1yGOcru8G+6DAa8Rs7EQ0HlumRwdjd"
    "iNyNFA4O8zhSOu0spup2sqW6TRSYCqVWTnbiLVTNz+FsupwPxtPReDjw6qFhJ1bml/HnL/"
    "Jw8Lwcz6b3jei3lRmcDs6Mp59m88cB/DKYQKda5OvKfJ7+Mp39Cu73DvhwjhFTUy62xhs5"
    "YR28Jwmwa/q5SbLXu3Lf8A5W5uDpaT77CjntH63MufQPaYi47x/lYUw/A1/6iWzpE1yh6Q"
    "MMc1ESfT3npVIW9fpfjq9YboEuaOXPQ6E1VLVoG0lLaf44no4Xy/FQXiznz8Pl8xz28qQr"
    "K/NxMH0eTOTBdDpbDlzRRpzKNRFlUSs6yWpFh1ArwHrBtn7kssjESEXAeAUB48K2dgG2NZ"
    "HSwT8fM43QiKmD2TpK0gqzaFodvqgdiX0DJJJYoM1ghI7Z9IT1OWp9JkdyQkW5pO4sII1D"
    "ShmvokpfSYkcReARc1xkxoSjLniqtA2Ij/QDxvWo+vDtYH5vfuwIwu+/YvEKybpHK6uQuP"
    "REDvTMfcB/iqHlh646lu3+HDi2SQ8S9Q7h7anC2+Pzj9HhEyMTtjUC0ByWS2G0TAM2LjQY"
    "gKWQ1hNYUVlEmKHyhXhFpu2j4rzIdsQ6O2ewV0yTKm6BWFcN/Sol6ovsdxyHfnngf6z3h1"
    "xiUPgjC7qyFX34DAx00NBhG1ZztHXVAthRlXyMLnaj0PVFpkHN1dHYSMis4+NkNQW0lwnQ"
    "XgqgPcoWfr6IYIATIxJghmCCeVR/eQHrHtnR/6Io9ktwNgFSkrQuwKbp7tJvS0xt9+H76X"
    "Hw298w1X0ym372b4/APZzMHujZRrvDemPs31KWUKmiNU5+7vvNum99sCmRlMm9Eqeqycan"
    "p+6PYiV/KSv5o5fwYu1+9Nq9+EU7n+DnXq7nW6dHwlRJz1ZhHkzC41Yf3Et1ZKYVfKTYMz"
    "6oD5ls1YiUYCSS+0raMiF8ZPOKmnZJ2jCSbhL2iyrsF1vFUd+OjFiPt1F1sLpXMW44G4Xl"
    "4+CXlSn9NgiK0IXHK3MwGQ8W9w304Qeu+9HqzWzcxNefWXKl2sm5Um0iV8rFGDz0xZWxFG"
    "VUV42tsqGPCxp5XCN16X/22qmb8j+ShuPHweSn3lU3VsbLx7tLrOgRKkBD9xZC9FV9sqEk"
    "gbwuK/sTuEHdRK5cq6cYqQjbFokVYh0sipbUfS2cUDKdFXGCVCDNYHXAVy1H2hsescb4Qz"
    "yrqYHoUnQjQ7roKNZ+cw5R+dnK7GSJzT+5ieLR3aOgmdVG4d9/lcNIEd0PoVgjBWGA8B7l"
    "lxcQxocKjQ8YJwiws5of4q1wWi7icbAcfoE5897Byvw0GE/gCfczj6Wh4C2vdduGQb2MpR"
    "5xqpo4Ek8QzwJ7Zq4lE0Yolr5i6SuWvqKmgBihiYzkbyV9PgocsY5mWaFkW3PPTH1pgT8n"
    "WXGXzZmC19tlrPGebEs7qM7ng6HpzdTVHXbnVcZ13c4lkl8h1SlWdP4D0WuI9Vxl6znD0b"
    "fyXv83y9ohSlPMuq10rHG/WZZ1Qyd52dAhVg1Yb2ZAMk4n/JCRhZh5eAHy52DrNjOuVGIB"
    "bmgzeHkBkl+l2H6TQ4+jNHWB8tSRxwdUesWAv+GAjKQUC1kywnRqgTUd652ty4e9LgMty/"
    "RM2FmBppAKlBNRVsE6jrUrx8gEunR0NfvwKr9YlhZ1rDABndyCwJyOuaLBwiK6bOs54KYS"
    "C6QT8sIccP2I+TCJXuBNxxuty4wthIwxrYykrIlHSKSWCb/CufkVBGPzMzZIDMpt/i7DeL"
    "tQXnTnPWk3LOp9VxkNt3tEUt7GWCiDjW1jLHqIGSJGw+IqvlvIH4n7X5G3CktxVZbiaE/I"
    "aoeL0tRFayt7QyxsIOQJnsIaqDpx62kufZ4OpsNvMrZzEto6JPnayhx8ligUtLMrU5qMpP"
    "nkW7gLU+zEyhzNFlJ4OfoNXHueo3Yi12NnwD2DMWgO6IUypAV3YN9hEtpw/DSG23SFvyF+"
    "qpmjd3Vusth247NnxLR7IzboOv8NuqBTFrKKuYYNQVgXGXzqZZ3YAk1sgcbfKBBboIkt0M"
    "QWaJcQDCnMimdhfeLarChG6DEjVKRcc5IILBJYT5nAKjaXSsIcn78tUzMS/NsskNBcAUO/"
    "7Xr1STwSoIj+QgOnjvX9T1S4jtaDMnqfsC7H6oaS8cFQXvm66EObV5FBKL/a1mEHpnL8rG"
    "VroBHSXxXe8R2cd2m2O8U29pBoB3uVZQvPU3WeJzpjccAXW2WzSYSc3kLN9K7rzu1NgDv8"
    "kob04nEwmZD1a+KjITeOAflFg+gLjDwWM7KVqs1lob8OrJaWz4uoB8894/rtRoNvC9dXB4"
    "/cc9+kwdw7iQ59n1rUn+b60gLvm9sM9hV58mAb0CuDHHn+F/CUkWuv826fz56XoGXa2ai/"
    "DrzBAnxG/XXeqVxGvMIzh2hTTe4ORW2q6l4l/ROA/8+VOQFMmCzhpwQPAJc+gzOfl/BTgg"
    "fgzIO0/FWSpvcN72BlBvw7gmsFF9z4oWyAVrI1KL6I1IKeGN15VvJsdxlKeXp4KH/lw9Gl"
    "Ezh6eLBWQsWpahLue4LUOPA2TDj699cSwess89l18nx2Tc5nwpNxnp6MhMX+EbU7yGZqtp"
    "bgpSJm3BBypDE8KR6ZPz7kqNtBdjqeNtBMMXFmNN1l2UozAY4SN9RM7qtiW806iaOrFCud"
    "2FazwLgssa3mxxG0YlvNysAU22qeIn1abKv5AexiW02R+yyW9mJpX0tdWiztL2ppvzjsdh"
    "sdKueZdpRMu/0qbXG/DwhPtqNk5JHmARDo7uAWW0tyKXeuUtbwytY6mLTpPc0fFxKdqTOu"
    "w+CME+6jo9xHniL+4mPFaEcK6GoJZ0kbWtR5t9joxrBNAuez3DZWLLPOdJklUohOq+ZEZh"
    "VSQWWGPrkNgT3D0jZhrXDkujZcLU0jjfLHgqyr2uTOJnZ45CtBrniTwX//PyyC/ng="
)
