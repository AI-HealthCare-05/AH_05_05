from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
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
        CREATE TABLE IF NOT EXISTS `user_suppl_nutrient` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `dose_amount` DECIMAL(8,3) NOT NULL,
    `dose_unit` VARCHAR(20) NOT NULL,
    `start_date` DATE NOT NULL,
    `end_date` DATE,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: ACTIVE\nPAUSED: PAUSED\nCOMPLETED: COMPLETED' DEFAULT 'ACTIVE',
    `note` VARCHAR(500),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `supplement_nutrient_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_user_suppl__user_id_4a5cc9` (`user_id`, `supplement_nutrient_id`),
    CONSTRAINT `chk_user_suppl_dose_positive` CHECK (`dose_amount` > 0),
    CONSTRAINT `chk_user_suppl_date_range` CHECK (`end_date` IS NULL OR `end_date` >= `start_date`),
    CONSTRAINT `fk_user_sup_suppleme_45c5bd61` FOREIGN KEY (`supplement_nutrient_id`) REFERENCES `supplement_nutrients` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_user_sup_user_1edd5404` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_user_suppl__user_id_960087` (`user_id`, `status`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `user_suppl_nutrient_slots` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `slot` VARCHAR(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_suppl_nutrient_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_user_suppl__user_su_d927f2` (`user_suppl_nutrient_id`, `slot`),
    CONSTRAINT `fk_user_sup_user_sup_8183ddbf` FOREIGN KEY (`user_suppl_nutrient_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `user_suppl_nutrient_slots`;
        DROP TABLE IF EXISTS `user_suppl_nutrient`;
        DROP TABLE IF EXISTS `supplement_nutrients`;"""


MODELS_STATE = (
    "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"
    "Qyy/OZfflCmpgNX4uS0m2Q2u+kxK//w/RcK2rQ=="
)
