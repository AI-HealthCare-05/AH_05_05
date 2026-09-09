"""Merge concurrent challenge migration heads and upsert their reference data."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        INSERT INTO `common_code_groups`
            (`category`, `group_code`, `group_name`, `description`, `is_active`)
        VALUES
            ('CHL', 'BDG_TYPE', '배지유형', '챌린지 배지 유형', 1),
            ('CHL', 'CST_CHL_TYPE', '맞춤챌린지유형', '맞춤 챌린지 템플릿 유형', 1)
        ON DUPLICATE KEY UPDATE
            `category` = VALUES(`category`),
            `group_name` = VALUES(`group_name`),
            `description` = VALUES(`description`),
            `is_active` = VALUES(`is_active`);

        INSERT INTO `common_codes`
            (`group_id`, `detail_code`, `detail_name`, `description`, `sort_order`, `is_active`)
        SELECT code_group.`id`, seed.`detail_code`, seed.`detail_name`, NULL, seed.`sort_order`, 1
        FROM (
            SELECT 'BDG_TYPE' AS `group_code`, 'STANDARD' AS `detail_code`, '공식' AS `detail_name`, 0 AS `sort_order`
            UNION ALL SELECT 'BDG_TYPE', 'CUSTOM', '맞춤', 1
            UNION ALL SELECT 'CST_CHL_TYPE', 'MEDICATION', '복약', 0
            UNION ALL SELECT 'CST_CHL_TYPE', 'SUPPLEMENT', '영양제', 1
            UNION ALL SELECT 'CST_CHL_TYPE', 'VISIT', '진료 준비', 2
        ) AS seed
        JOIN `common_code_groups` AS code_group
          ON code_group.`category` = 'CHL'
         AND code_group.`group_code` = seed.`group_code`
        ON DUPLICATE KEY UPDATE
            `detail_name` = VALUES(`detail_name`),
            `description` = VALUES(`description`),
            `sort_order` = VALUES(`sort_order`),
            `is_active` = VALUES(`is_active`);

        INSERT INTO `badges` (`name`, `description`, `image_path`, `type`, `is_active`)
        SELECT seed.`name`, seed.`description`, seed.`image_path`, badge_type.`id`, 1
        FROM (
            SELECT '물마시기 배지' AS `name`, '물마시기 배지입니다.' AS `description`,
                   'media/badges/water-badge.png' AS `image_path`, 'STANDARD' AS `type_code`
            UNION ALL SELECT '스트레칭 배지', '스트레칭 배지입니다.',
                   'media/badges/stretching-badge.png', 'STANDARD'
            UNION ALL SELECT '걷기 배지', '걷기 배지입니다.',
                   'media/badges/walking-badge.png', 'STANDARD'
            UNION ALL SELECT '복약', '맞춤 챌린지용 - 복약',
                   'media/badges/5e23dabfba8942bfad086b844f134e0a.webp', 'CUSTOM'
            UNION ALL SELECT '영양제', '맞춤 챌린지용 - 영양제',
                   'media/badges/86bbb08f36e04d99849c6c9fa63fa73d.webp', 'CUSTOM'
            UNION ALL SELECT '진료준비', '맞춤 챌린지용 - 진료준비',
                   'media/badges/a33ef3d1e7fd48c9be8c242e4176ff51.webp', 'CUSTOM'
        ) AS seed
        JOIN `common_code_groups` AS badge_group
          ON badge_group.`category` = 'CHL'
         AND badge_group.`group_code` = 'BDG_TYPE'
        JOIN `common_codes` AS badge_type
          ON badge_type.`group_id` = badge_group.`id`
         AND badge_type.`detail_code` = seed.`type_code`
        ON DUPLICATE KEY UPDATE
            `description` = VALUES(`description`),
            `image_path` = VALUES(`image_path`),
            `type` = VALUES(`type`),
            `is_active` = VALUES(`is_active`);

        INSERT INTO `custom_challenge_templates`
            (`name`, `is_active`, `check_type_id`, `challenge_type`, `reward_badge_id`)
        SELECT seed.`name`, 1, check_type.`id`, challenge_type.`id`, reward_badge.`id`
        FROM (
            SELECT '복약 챌린지' AS `name`, 'MEDICATION' AS `challenge_type_code`, '복약' AS `badge_name`
            UNION ALL SELECT '영양제 챌린지', 'SUPPLEMENT', '영양제'
            UNION ALL SELECT '다음 진료 챌린지', 'VISIT', '진료준비'
        ) AS seed
        JOIN `common_code_groups` AS check_group
          ON check_group.`category` = 'CHL'
         AND check_group.`group_code` = 'CST_CHK_TYPE'
        JOIN `common_codes` AS check_type
          ON check_type.`group_id` = check_group.`id`
         AND check_type.`detail_code` = 'AUTO'
        JOIN `common_code_groups` AS challenge_group
          ON challenge_group.`category` = 'CHL'
         AND challenge_group.`group_code` = 'CST_CHL_TYPE'
        JOIN `common_codes` AS challenge_type
          ON challenge_type.`group_id` = challenge_group.`id`
         AND challenge_type.`detail_code` = seed.`challenge_type_code`
        JOIN `badges` AS reward_badge ON reward_badge.`name` = seed.`badge_name`
        ON DUPLICATE KEY UPDATE
            `is_active` = VALUES(`is_active`),
            `check_type_id` = VALUES(`check_type_id`),
            `challenge_type` = VALUES(`challenge_type`),
            `reward_badge_id` = VALUES(`reward_badge_id`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Upserted reference rows can predate this migration and may already be in use.
    return "SELECT 1;"


_feature_state = decompress_dict(
    import_module("app.core.db.migrations.models.41_20260909000001_add_custom_challenge_and_badge_types").MODELS_STATE
)
_state = deepcopy(
    decompress_dict(
        import_module("app.core.db.migrations.models.41_20260909120000_challenge_rejoin_attempts").MODELS_STATE
    )
)

for _model_name in ("models.Badge", "models.CustomChallengeTemplate"):
    for _key in ("indexes", "data_fields", "fk_fields"):
        _state[_model_name][_key] = deepcopy(_feature_state[_model_name][_key])

_state["models.Badge"]["backward_fk_fields"] = deepcopy(_feature_state["models.Badge"]["backward_fk_fields"])

_common_code_relations = {
    relation["name"]: deepcopy(relation) for relation in _state["models.CommonCode"]["backward_fk_fields"]
}
_common_code_relations.update(
    {relation["name"]: deepcopy(relation) for relation in _feature_state["models.CommonCode"]["backward_fk_fields"]}
)
_common_code_relation_order = (
    "typed_badges",
    "period_challenges",
    "typed_challenges",
    "check_frequency_challenges",
    "check_type_challenges",
    "typed_custom_challenge_templates",
    "custom_challenge_templates",
)
_state["models.CommonCode"]["backward_fk_fields"] = [
    _common_code_relations[name] for name in _common_code_relation_order
]

MODELS_STATE = compress_dict(_state)
