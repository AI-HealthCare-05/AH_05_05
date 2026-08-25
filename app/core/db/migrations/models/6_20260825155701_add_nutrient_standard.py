from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
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
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `nutrient_standard`;"""


MODELS_STATE = (
    "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"
    "P2YlpV//D3cl46Y="
)
