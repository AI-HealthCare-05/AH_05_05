"""Retire legacy care guides; preserve removed data in explicit backup tables.

Apply only with API/workers stopped and a verified encrypted database snapshot.
MySQL DDL is non-transactional. Existing backup tables deliberately stop a retry;
never drop them automatically. See docs/ocr/erd125-care-migration-20260908.md.
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = False

REMOVED_SOURCE_PREDICATE = """`care_advice_id` IS NOT NULL
    OR `patient_source_kind` = 'CARE_ADVICE'
    OR `patient_field` IN ('DIAGNOSIS', 'SURGERY', 'DISCHARGE_DATE')"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    return f"""
        CREATE TABLE `_m39_backup_care_episode_removed` AS
        SELECT `id`, `title`, `diagnosis`, `surgery`, `discharge_date`,
               `started_at`, `default_end_at`, `planned_end_at`, `alias`
        FROM `care_episodes`;
        ALTER TABLE `_m39_backup_care_episode_removed` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_care_advices` AS SELECT * FROM `care_advices`;
        ALTER TABLE `_m39_backup_care_advices` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_recovery_guides` AS SELECT * FROM `recovery_guides`;
        ALTER TABLE `_m39_backup_recovery_guides` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_recovery_guide_sources` AS SELECT * FROM `recovery_guide_sources`;
        ALTER TABLE `_m39_backup_recovery_guide_sources` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_chat_message_sources_removed` AS
        SELECT * FROM `chat_message_sources` WHERE {REMOVED_SOURCE_PREDICATE};
        ALTER TABLE `_m39_backup_chat_message_sources_removed` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_chat_message_guide` AS
        SELECT `id`, `guide_id` FROM `chat_messages` WHERE `guide_id` IS NOT NULL;
        ALTER TABLE `_m39_backup_chat_message_guide` ADD PRIMARY KEY (`id`);
        CREATE TABLE `_m39_backup_alarm_source_guide` AS
        SELECT `id`, `source_guide_id` FROM `alarms` WHERE `source_guide_id` IS NOT NULL;
        ALTER TABLE `_m39_backup_alarm_source_guide` ADD PRIMARY KEY (`id`);

        CREATE TEMPORARY TABLE `_m39_backup_guard` (`ok` BOOL NOT NULL CHECK (`ok` = 1));
        INSERT INTO `_m39_backup_guard` (`ok`) SELECT
          (SELECT COUNT(*) FROM `_m39_backup_care_episode_removed`) = (SELECT COUNT(*) FROM `care_episodes`)
          AND (SELECT COUNT(*) FROM `_m39_backup_care_advices`) = (SELECT COUNT(*) FROM `care_advices`)
          AND (SELECT COUNT(*) FROM `_m39_backup_recovery_guides`) = (SELECT COUNT(*) FROM `recovery_guides`)
          AND (SELECT COUNT(*) FROM `_m39_backup_recovery_guide_sources`) = (SELECT COUNT(*) FROM `recovery_guide_sources`)
          AND (SELECT COUNT(*) FROM `_m39_backup_chat_message_sources_removed`) =
              (SELECT COUNT(*) FROM `chat_message_sources` WHERE {REMOVED_SOURCE_PREDICATE})
          AND (SELECT COUNT(*) FROM `_m39_backup_chat_message_guide`) =
              (SELECT COUNT(*) FROM `chat_messages` WHERE `guide_id` IS NOT NULL)
          AND (SELECT COUNT(*) FROM `_m39_backup_alarm_source_guide`) =
              (SELECT COUNT(*) FROM `alarms` WHERE `source_guide_id` IS NOT NULL);
        DROP TEMPORARY TABLE `_m39_backup_guard`;

        ALTER TABLE `care_episodes` MODIFY COLUMN `alias` VARCHAR(255) NULL COMMENT '복약 별칭';
        UPDATE `care_episodes` SET `alias` = CASE
          WHEN NULLIF(TRIM(`alias`), '') IS NOT NULL THEN TRIM(`alias`)
          WHEN NULLIF(TRIM(`hospital_name`), '') IS NOT NULL THEN `hospital_name`
          ELSE NULL END;

        DELETE FROM `chat_message_sources` WHERE {REMOVED_SOURCE_PREDICATE};
        ALTER TABLE `chat_message_sources`
          DROP CHECK `chk_chat_patient_source`,
          DROP FOREIGN KEY `fk_chat_mes_care_adv_d6cc90e0`,
          DROP INDEX `idx_chat_messag_care_ad_c38653`,
          DROP COLUMN `care_advice_id`,
          MODIFY COLUMN `patient_source_kind` VARCHAR(18) NULL
            COMMENT 'CARE_EPISODE_FIELD: CARE_EPISODE_FIELD\\nMEDICATION: MEDICATION\\nFOLLOW_UP_VISIT: FOLLOW_UP_VISIT',
          MODIFY COLUMN `patient_field` VARCHAR(15) NULL COMMENT 'MEDICATION_DAYS: MEDICATION_DAYS',
          ADD CONSTRAINT `chk_chat_patient_source` CHECK (
            (`source_type` = 'PATIENT_SAVED_FIELD'
             AND `patient_source_kind` IS NOT NULL
             AND `user_suppl_nutrient_id` IS NULL AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL
             AND ((`patient_source_kind` = 'CARE_EPISODE_FIELD'
                   AND `patient_field` IS NOT NULL AND `patient_field` = 'MEDICATION_DAYS'
                   AND `care_episode_id` IS NOT NULL AND `medication_id` IS NULL AND `follow_up_visit_id` IS NULL)
               OR (`patient_source_kind` = 'MEDICATION' AND `patient_field` IS NULL
                   AND `care_episode_id` IS NULL AND `medication_id` IS NOT NULL AND `follow_up_visit_id` IS NULL)
               OR (`patient_source_kind` = 'FOLLOW_UP_VISIT' AND `patient_field` IS NULL
                   AND `care_episode_id` IS NULL AND `medication_id` IS NULL AND `follow_up_visit_id` IS NOT NULL)))
            OR (`source_type` = 'PUBLIC_RAG_CHUNK'
                AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL
                AND `medication_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL
                AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL)
            OR (`source_type` = 'USER_SUPPLEMENT'
                AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL
                AND `medication_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NOT NULL
                AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NULL)
            OR (`source_type` = 'INTERACTION_RULE'
                AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL
                AND `medication_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL
                AND `interaction_rule_id` IS NOT NULL AND `medication_safety_rule_id` IS NULL)
            OR (`source_type` = 'MEDICATION_SAFETY_RULE'
                AND `patient_source_kind` IS NULL AND `patient_field` IS NULL AND `care_episode_id` IS NULL
                AND `medication_id` IS NULL AND `follow_up_visit_id` IS NULL AND `user_suppl_nutrient_id` IS NULL
                AND `interaction_rule_id` IS NULL AND `medication_safety_rule_id` IS NOT NULL)
          );

        ALTER TABLE `chat_messages`
          DROP FOREIGN KEY `fk_chat_mes_recovery_6732baf3`,
          DROP INDEX `idx_chat_messag_guide_i_99461b`,
          DROP COLUMN `guide_id`;
        ALTER TABLE `alarms`
          DROP FOREIGN KEY `fk_alarms_recovery_35468ea9`,
          DROP COLUMN `source_guide_id`;
        DROP TABLE `recovery_guide_sources`;
        DROP TABLE `recovery_guides`;
        DROP TABLE `care_advices`;
        ALTER TABLE `care_episodes`
          DROP CHECK `chk_care_episode_default_end`,
          DROP CHECK `chk_care_episode_planned_end`,
          DROP CHECK `chk_care_episode_completed`,
          DROP INDEX `idx_care_episod_user_id_0c2355`,
          DROP COLUMN `title`,
          DROP COLUMN `diagnosis`,
          DROP COLUMN `surgery`,
          DROP COLUMN `discharge_date`,
          DROP COLUMN `started_at`,
          DROP COLUMN `default_end_at`,
          DROP COLUMN `planned_end_at`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    raise RuntimeError(
        "Migration 39 is intentionally irreversible: automatic rollback can lose post-upgrade data. "
        "Keep _m39_backup_* tables and follow docs/ocr/erd125-care-migration-20260908.md."
    )


MODELS_STATE = (
    "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"
)
