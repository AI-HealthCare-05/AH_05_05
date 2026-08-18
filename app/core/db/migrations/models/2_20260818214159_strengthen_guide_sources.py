from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_public_source`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_public_source`;
        ALTER TABLE `recovery_guides` ADD `safety_reason_codes` JSON NOT NULL;
        ALTER TABLE `recovery_guides` DROP COLUMN `safety_reason_code`;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `model_name` VARCHAR(100) NOT NULL;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `prompt_version` VARCHAR(100) NOT NULL;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `schema_version` VARCHAR(50) NOT NULL;
        ALTER TABLE `recovery_guides` ALTER COLUMN `safety_status` DROP DEFAULT;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `guide_content` JSON NOT NULL;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `completed_at` DATETIME(6) NOT NULL;
        ALTER TABLE `recovery_guide_sources` ADD `source_license` VARCHAR(255);
        ALTER TABLE `recovery_guide_sources` ADD `source_page_number` INT;
        ALTER TABLE `chat_message_sources` ADD `source_license` VARCHAR(255);
        ALTER TABLE `chat_message_sources` ADD `source_page_number` INT;
        ALTER TABLE `recovery_guides` ADD CONSTRAINT `chk_guide_safety_complete` CHECK (`safety_status` <> 'PENDING');
        ALTER TABLE `recovery_guides` ADD CONSTRAINT `chk_guide_superseded_status` CHECK ((`status` = 'COMPLETED' AND `superseded_at` IS NULL) OR (`status` = 'SUPERSEDED' AND `superseded_at` IS NOT NULL));
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `source_page_number` IS NULL AND `source_license` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_source_page` CHECK (`source_page_number` IS NULL OR `source_page_number` >= 1);
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `source_page_number` IS NULL AND `source_license` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_source_page` CHECK (`source_page_number` IS NULL OR `source_page_number` >= 1);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_source_page`;
        ALTER TABLE `chat_message_sources` DROP CHECK `chk_chat_public_source`;
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_source_page`;
        ALTER TABLE `recovery_guide_sources` DROP CHECK `chk_guide_public_source`;
        ALTER TABLE `recovery_guides` DROP CHECK `chk_guide_superseded_status`;
        ALTER TABLE `recovery_guides` DROP CHECK `chk_guide_safety_complete`;
        ALTER TABLE `recovery_guides` ADD `safety_reason_code` VARCHAR(100);
        ALTER TABLE `recovery_guides` DROP COLUMN `safety_reason_codes`;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `model_name` VARCHAR(100);
        ALTER TABLE `recovery_guides` MODIFY COLUMN `prompt_version` VARCHAR(100);
        ALTER TABLE `recovery_guides` MODIFY COLUMN `schema_version` VARCHAR(50);
        ALTER TABLE `recovery_guides` ALTER COLUMN `safety_status` SET DEFAULT 'PENDING';
        ALTER TABLE `recovery_guides` MODIFY COLUMN `guide_content` JSON;
        ALTER TABLE `recovery_guides` MODIFY COLUMN `completed_at` DATETIME(6);
        ALTER TABLE `chat_message_sources` DROP COLUMN `source_license`;
        ALTER TABLE `chat_message_sources` DROP COLUMN `source_page_number`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `source_license`;
        ALTER TABLE `recovery_guide_sources` DROP COLUMN `source_page_number`;
        ALTER TABLE `recovery_guide_sources` ADD CONSTRAINT `chk_guide_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL AND `source_field` IS NOT NULL AND `chunk_type` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `similarity_score` IS NULL));
        ALTER TABLE `chat_message_sources` ADD CONSTRAINT `chk_chat_public_source` CHECK ((`source_type` = 'PUBLIC_RAG_CHUNK' AND `public_dataset_key` IS NOT NULL AND `dataset_version` IS NOT NULL AND `vector_chunk_id` IS NOT NULL AND `source_record_key` IS NOT NULL AND `source_field` IS NOT NULL AND `chunk_type` IS NOT NULL) OR (`source_type` = 'PATIENT_SAVED_FIELD' AND `public_dataset_key` IS NULL AND `dataset_version` IS NULL AND `vector_chunk_id` IS NULL AND `source_record_key` IS NULL AND `source_field` IS NULL AND `chunk_type` IS NULL AND `source_title` IS NULL AND `source_organization` IS NULL AND `source_url` IS NULL AND `similarity_score` IS NULL));"""


MODELS_STATE = (
    "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"
    "jZ"
)
