"""#364: add source-backed therapeutic classifications for registered intake retrieval."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `therapeutic_classes` (
            `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `code` VARCHAR(100) NOT NULL UNIQUE,
            `display_name` VARCHAR(255) NOT NULL,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_therapeutic_class_display` (`display_name`)
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `therapeutic_class_aliases` (
            `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `alias` VARCHAR(255) NOT NULL,
            `normalized_alias` VARCHAR(255) NOT NULL,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `therapeutic_class_id` BIGINT NOT NULL,
            UNIQUE KEY `uid_therapeutic_class_alias` (`therapeutic_class_id`, `normalized_alias`),
            CONSTRAINT `fk_therapeutic_alias_class` FOREIGN KEY (`therapeutic_class_id`)
                REFERENCES `therapeutic_classes` (`id`) ON DELETE CASCADE,
            KEY `idx_therapeutic_alias_normalized` (`normalized_alias`)
        ) CHARACTER SET utf8mb4;
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
            UNIQUE KEY `uid_interaction_therapeutic_class` (
                `interaction_entity_id`, `therapeutic_class_id`, `classification_dataset_version`
            ),
            CONSTRAINT `fk_interaction_therapeutic_entity` FOREIGN KEY (`interaction_entity_id`)
                REFERENCES `interaction_entities` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_interaction_therapeutic_class` FOREIGN KEY (`therapeutic_class_id`)
                REFERENCES `therapeutic_classes` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `chk_interaction_therapeutic_approval` CHECK (
                (`review_status` = 'APPROVED' AND `approved_at` IS NOT NULL)
                OR (`review_status` <> 'APPROVED' AND `approved_at` IS NULL)
            ),
            KEY `idx_interaction_therapeutic_review` (`therapeutic_class_id`, `review_status`),
            KEY `idx_interaction_therapeutic_version` (`classification_dataset_version`)
        ) CHARACTER SET utf8mb4;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `interaction_entity_therapeutic_classes`;
        DROP TABLE IF EXISTS `therapeutic_class_aliases`;
        DROP TABLE IF EXISTS `therapeutic_classes`;
    """


_previous_state = decompress_dict(
    import_module("app.core.db.migrations.models.41_20260909120000_challenge_rejoin_attempts").MODELS_STATE
)
_state = deepcopy(_previous_state)


def _copy_field(source: dict, *, name: str, db_column: str | None = None) -> dict:
    field = deepcopy(source)
    field["name"] = name
    field["db_column"] = db_column or name
    return field


_entity_state = _state["models.InteractionEntity"]
_alias_state = _state["models.InteractionEntityAlias"]
_rule_state = _state["models.InteractionRule"]
_rule_source_state = _state["models.InteractionRuleSource"]
_medication_guide_state = _state["models.MedicationProductGuide"]

_bigint_pk = deepcopy(_entity_state["pk_field"])
_char_template = deepcopy(_entity_state["data_fields"][1])
_created_at_template = deepcopy(_entity_state["data_fields"][3])
_updated_at_template = deepcopy(_medication_guide_state["data_fields"][-1])
_enum_template = deepcopy(_rule_state["data_fields"][3])
_text_template = deepcopy(_rule_source_state["data_fields"][3])
_id_template = deepcopy(_alias_state["data_fields"][-1])
_fk_template = deepcopy(_alias_state["fk_fields"][0])
_backward_template = deepcopy(_entity_state["backward_fk_fields"][0])


def _char_field(name: str, max_length: int, *, unique: bool = False, indexed: bool = False) -> dict:
    field = _copy_field(_char_template, name=name)
    field["constraints"] = {"max_length": max_length}
    field["db_field_types"] = {"": f"VARCHAR({max_length})", "oracle": f"NVARCHAR2({max_length})"}
    field["unique"] = unique
    field["indexed"] = indexed
    return field


def _foreign_key(*, name: str, python_type: str, raw_field: str, on_delete: str) -> dict:
    field = deepcopy(_fk_template)
    field.update(
        {
            "name": name,
            "python_type": python_type,
            "raw_field": raw_field,
            "on_delete": on_delete,
        }
    )
    return field


def _backward_relation(*, name: str, python_type: str) -> dict:
    field = deepcopy(_backward_template)
    field.update({"name": name, "python_type": python_type})
    return field


_therapeutic_class_state = {
    "name": "models.TherapeuticClass",
    "app": "models",
    "table": "therapeutic_classes",
    "abstract": False,
    "description": "검수 가능한 약물 치료군의 안정적인 기준 용어.",
    "docstring": "검수 가능한 약물 치료군의 안정적인 기준 용어.",
    "unique_together": [],
    "indexes": [["display_name"]],
    "pk_field": deepcopy(_bigint_pk),
    "data_fields": [
        _char_field("code", 100, unique=True, indexed=True),
        _char_field("display_name", 255),
        _copy_field(_created_at_template, name="created_at"),
        _copy_field(_updated_at_template, name="updated_at"),
    ],
    "fk_fields": [],
    "backward_fk_fields": [
        _backward_relation(
            name="aliases",
            python_type="models.TherapeuticClassAlias",
        ),
        _backward_relation(
            name="entity_classifications",
            python_type="models.InteractionEntityTherapeuticClass",
        ),
    ],
    "o2o_fields": [],
    "backward_o2o_fields": [],
    "m2m_fields": [],
    "managed": None,
}

_therapeutic_class_alias_state = {
    "name": "models.TherapeuticClassAlias",
    "app": "models",
    "table": "therapeutic_class_aliases",
    "abstract": False,
    "description": "사용자 질문에서 치료군을 식별하는 검수된 표현.",
    "docstring": "사용자 질문에서 치료군을 식별하는 검수된 표현.",
    "unique_together": [["therapeutic_class", "normalized_alias"]],
    "indexes": [["normalized_alias"]],
    "pk_field": deepcopy(_bigint_pk),
    "data_fields": [
        _char_field("alias", 255),
        _char_field("normalized_alias", 255),
        _copy_field(_created_at_template, name="created_at"),
        _copy_field(_id_template, name="therapeutic_class_id"),
    ],
    "fk_fields": [
        _foreign_key(
            name="therapeutic_class",
            python_type="models.TherapeuticClass",
            raw_field="therapeutic_class_id",
            on_delete="CASCADE",
        )
    ],
    "backward_fk_fields": [],
    "o2o_fields": [],
    "backward_o2o_fields": [],
    "m2m_fields": [],
    "managed": None,
}

_classification_review_status = _copy_field(_enum_template, name="review_status")
_classification_review_status["default"] = "PENDING"
_classification_source_url = _copy_field(_text_template, name="source_url")
_classification_source_url["nullable"] = True
_classification_state = {
    "name": "models.InteractionEntityTherapeuticClass",
    "app": "models",
    "table": "interaction_entity_therapeutic_classes",
    "abstract": False,
    "description": "상호작용 엔터티와 치료군을 출처·검수 상태와 함께 연결한다.",
    "docstring": "상호작용 엔터티와 치료군을 출처·검수 상태와 함께 연결한다.",
    "unique_together": [["interaction_entity", "therapeutic_class", "classification_dataset_version"]],
    "indexes": [["therapeutic_class", "review_status"], ["classification_dataset_version"]],
    "pk_field": deepcopy(_bigint_pk),
    "data_fields": [
        _classification_review_status,
        _char_field("classification_dataset_version", 100),
        _char_field("source_id", 100),
        _char_field("document_id", 150),
        _char_field("record_id", 150),
        _copy_field(_text_template, name="raw_classification_text"),
        _classification_source_url,
        _copy_field(_rule_state["data_fields"][6], name="approved_at"),
        _copy_field(_created_at_template, name="created_at"),
        _copy_field(_entity_state["data_fields"][4], name="updated_at"),
        _copy_field(_id_template, name="interaction_entity_id"),
        _copy_field(_id_template, name="therapeutic_class_id"),
    ],
    "fk_fields": [
        _foreign_key(
            name="interaction_entity",
            python_type="models.InteractionEntity",
            raw_field="interaction_entity_id",
            on_delete="RESTRICT",
        ),
        _foreign_key(
            name="therapeutic_class",
            python_type="models.TherapeuticClass",
            raw_field="therapeutic_class_id",
            on_delete="RESTRICT",
        ),
    ],
    "backward_fk_fields": [],
    "o2o_fields": [],
    "backward_o2o_fields": [],
    "m2m_fields": [],
    "managed": None,
}

_state["models.TherapeuticClass"] = _therapeutic_class_state
_state["models.TherapeuticClassAlias"] = _therapeutic_class_alias_state
_state["models.InteractionEntityTherapeuticClass"] = _classification_state
_state["models.InteractionEntity"]["backward_fk_fields"].append(
    _backward_relation(
        name="therapeutic_classifications",
        python_type="models.InteractionEntityTherapeuticClass",
    )
)

MODELS_STATE = compress_dict(_state)
