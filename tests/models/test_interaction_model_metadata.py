from decimal import Decimal
from importlib import import_module

import pytest
from tortoise import Tortoise, fields


def load_interaction_models():
    try:
        enums = import_module("app.models.enums")
        interactions = import_module("app.models.interactions")
        chat = import_module("app.models.chat")
    except ModuleNotFoundError as exc:
        pytest.fail(f"interaction model module is missing: {exc.name}")

    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.care",
            "app.models.ocr",
            "app.models.recovery",
            "app.models.medications",
            "app.models.supplement_nutrients",
            "app.models.interactions",
            "app.models.chat",
        ),
        "models",
    )
    return enums, interactions, chat


def test_interaction_enums_cover_supported_pairs_and_review_states() -> None:
    enums, _, _ = load_interaction_models()

    assert {item.value for item in enums.InteractionEntityKind} == {
        "DRUG",
        "SUPPLEMENT",
        "FOOD",
    }
    assert {item.value for item in enums.InteractionPairType} == {
        "DRUG_DRUG",
        "DRUG_SUPPLEMENT",
        "SUPPLEMENT_SUPPLEMENT",
        "DRUG_FOOD",
    }
    assert {item.value for item in enums.InteractionReviewStatus} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }
    assert {item.value for item in enums.InteractionExtractionMethod} == {
        "DETERMINISTIC_STRUCTURED",
        "MANUAL_ANNOTATION",
    }


def test_interaction_entity_models_preserve_normalized_identity() -> None:
    enums, interactions, _ = load_interaction_models()

    entity = interactions.InteractionEntity
    alias = interactions.InteractionEntityAlias
    identifier = interactions.InteractionEntityIdentifier

    assert entity._meta.db_table == "interaction_entities"
    assert entity._meta.unique_together == (("entity_kind", "normalized_name"),)
    assert entity._meta.fields_map["entity_kind"].enum_type is enums.InteractionEntityKind
    assert alias._meta.db_table == "interaction_entity_aliases"
    assert alias._meta.unique_together == (("interaction_entity", "normalized_alias"),)
    assert alias._meta.fields_map["interaction_entity"].on_delete == fields.CASCADE
    assert identifier._meta.db_table == "interaction_entity_identifiers"
    assert identifier._meta.unique_together == (
        ("source_id", "source_code"),
        ("interaction_entity", "source_id"),
    )


def test_medication_and_supplement_mappings_do_not_modify_source_models() -> None:
    enums, interactions, _ = load_interaction_models()

    mapping = interactions.MedicationInteractionMapping
    medication_entity = interactions.MedicationInteractionEntity
    supplement_entity = interactions.SupplementInteractionEntity

    assert mapping._meta.db_table == "medication_interaction_mappings"
    assert mapping._meta.fields_map["medication"].unique is True
    assert mapping._meta.fields_map["mapping_status"].default is enums.InteractionMappingStatus.PENDING
    assert medication_entity._meta.unique_together == (("medication", "interaction_entity"),)
    confidence = medication_entity._meta.fields_map["match_confidence"]
    assert confidence.max_digits == 5
    assert confidence.decimal_places == 4
    assert {validator.min_value for validator in confidence.validators if hasattr(validator, "min_value")} == {
        Decimal("0")
    }
    assert {validator.max_value for validator in confidence.validators if hasattr(validator, "max_value")} == {
        Decimal("1")
    }
    assert supplement_entity._meta.unique_together == (("supplement_nutrient", "interaction_entity"),)
    assert supplement_entity._meta.fields_map["supplement_nutrient"].on_delete == fields.CASCADE
    assert supplement_entity._meta.fields_map["interaction_entity"].on_delete == fields.RESTRICT


def test_interaction_rules_keep_structured_decision_and_evidence_separate() -> None:
    enums, interactions, _ = load_interaction_models()

    rule = interactions.InteractionRule
    source = interactions.InteractionRuleSource
    evidence = interactions.InteractionRuleEvidenceChunk

    assert rule._meta.db_table == "interaction_rules"
    assert rule._meta.fields_map["pair_key"].unique is False
    assert ("pair_key", "rule_dataset_version") in rule._meta.unique_together
    assert rule._meta.fields_map["left_entity"].on_delete == fields.RESTRICT
    assert rule._meta.fields_map["right_entity"].on_delete == fields.RESTRICT
    assert rule._meta.fields_map["review_status"].default is enums.InteractionReviewStatus.PENDING
    assert rule._meta.fields_map["extraction_method"].enum_type is enums.InteractionExtractionMethod
    assert "raw_effect_text" not in rule._meta.fields_map
    assert source._meta.db_table == "interaction_rule_sources"
    assert source._meta.unique_together == (("interaction_rule", "source_id", "document_id", "record_id"),)
    assert source._meta.fields_map["raw_effect_text"].null is False
    assert evidence._meta.db_table == "interaction_rule_evidence_chunks"
    assert evidence._meta.unique_together == (("interaction_rule_source", "dataset_version", "vector_chunk_id"),)


def test_chat_models_trace_interaction_sources_and_latency() -> None:
    enums, _, chat = load_interaction_models()

    assert enums.ChatRouteType.INTERACTION.value == "INTERACTION"
    assert {item.value for item in enums.ChatSourceType} >= {
        "USER_SUPPLEMENT",
        "INTERACTION_RULE",
    }
    duration = chat.ChatMessage._meta.fields_map["duration_ms"]
    assert duration.null is True
    assert duration.validators[0].min_value == 0
    assert (
        "user",
        "status",
        "last_message_at",
    ) in chat.ChatSession._meta.indexes
    user_supplement = chat.ChatMessageSource._meta.fields_map["user_suppl_nutrient"]
    assert user_supplement.model_name == "models.UserSupplementNutrient"
    assert user_supplement.on_delete == fields.RESTRICT
    interaction_rule = chat.ChatMessageSource._meta.fields_map["interaction_rule"]
    assert interaction_rule.model_name == "models.InteractionRule"
    assert interaction_rule.on_delete == fields.RESTRICT
    care_episode = chat.ChatMessageSource._meta.fields_map["care_episode"]
    assert care_episode.model_name == "models.CareEpisode"
    assert care_episode.null is True
    assert care_episode.on_delete == fields.RESTRICT
    assert ("care_episode",) in chat.ChatMessageSource._meta.indexes
    assert chat.ChatMessageSource._meta.fields_map["source_record_key"].max_length == 100


def test_tortoise_registers_all_interaction_tables() -> None:
    from app.core.db.databases import TORTOISE_APP_MODELS

    expected_tables = {
        "interaction_entities",
        "interaction_entity_aliases",
        "interaction_entity_identifiers",
        "medication_interaction_mappings",
        "medication_interaction_entities",
        "supplement_interaction_entities",
        "interaction_rules",
        "interaction_rule_sources",
        "interaction_rule_evidence_chunks",
    }

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    registered_tables = {model._meta.db_table for model in Tortoise.apps["models"].values()}

    assert expected_tables <= registered_tables
