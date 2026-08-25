from importlib import import_module

MIGRATION = import_module("app.core.db.migrations.models.7_20260825203757_add_ai_interaction_chat_schema")


async def test_upgrade_replaces_chat_source_checks_for_all_source_types() -> None:
    sql = await MIGRATION.upgrade(None)

    drop_patient = sql.index("DROP CHECK `chk_chat_patient_source`")
    drop_public = sql.index("DROP CHECK `chk_chat_public_source`")
    add_patient = sql.index("ADD CONSTRAINT `chk_chat_patient_source`")
    add_public = sql.index("ADD CONSTRAINT `chk_chat_public_source`")

    assert drop_patient < add_patient
    assert drop_public < add_public

    patient_check = sql[add_patient : sql.index(";", add_patient)]
    public_check = sql[add_public : sql.index(";", add_public)]

    assert "'PATIENT_SAVED_FIELD'" in patient_check
    assert "'PUBLIC_RAG_CHUNK'" in patient_check
    assert "'USER_SUPPLEMENT'" in patient_check
    assert "'INTERACTION_RULE'" in patient_check
    assert "`source_type` <> 'PUBLIC_RAG_CHUNK'" in public_check


async def test_upgrade_adds_ai_interaction_domain_checks() -> None:
    sql = await MIGRATION.upgrade(None)

    expected_constraints = (
        "chk_interaction_rule_entities",
        "chk_interaction_rule_approval",
        "chk_interaction_pair_key",
        "chk_medication_interaction_confidence",
        "chk_supplement_interaction_amount",
        "chk_supplement_interaction_amount_unit",
        "chk_chat_duration_ms",
        "chk_chat_similarity_score",
    )

    for constraint in expected_constraints:
        assert f"CONSTRAINT `{constraint}`" in sql


async def test_downgrade_drops_children_before_parent_tables() -> None:
    sql = await MIGRATION.downgrade(None)

    expected_order = (
        "interaction_rule_evidence_chunks",
        "interaction_rule_sources",
        "interaction_rules",
        "medication_interaction_entities",
        "supplement_interaction_entities",
        "medication_interaction_mappings",
        "interaction_entity_aliases",
        "interaction_entity_identifiers",
        "interaction_entities",
    )
    positions = [sql.index(f"DROP TABLE IF EXISTS `{table}`") for table in expected_order]

    assert positions == sorted(positions)


async def test_downgrade_drops_foreign_keys_before_their_indexes() -> None:
    sql = await MIGRATION.downgrade(None)

    foreign_key_and_index_pairs = (
        ("fk_chat_mes_care_epi_e6e04ad2", "idx_chat_messag_care_ep_a7d8ed"),
        ("fk_chat_mes_interact_65e4a78b", "idx_chat_messag_interac_8c6fd1"),
        ("fk_chat_mes_user_sup_4624a86e", "idx_chat_messag_user_su_360dbe"),
    )

    for foreign_key, index in foreign_key_and_index_pairs:
        assert sql.index(f"DROP FOREIGN KEY `{foreign_key}`") < sql.index(f"DROP INDEX `{index}`")


async def test_downgrade_restores_user_fk_index_before_dropping_composite() -> None:
    sql = await MIGRATION.downgrade(None)

    restore_user_index = sql.index("ADD INDEX `fk_chat_ses_user_91ae8bac` (`user_id`)")
    drop_composite_index = sql.index("DROP INDEX `idx_chat_sessio_user_id_5d846b`")

    assert restore_user_index < drop_composite_index


async def test_downgrade_restores_legacy_chat_source_checks() -> None:
    sql = await MIGRATION.downgrade(None)

    drop_patient = sql.index("DROP CHECK `chk_chat_patient_source`")
    drop_public = sql.index("DROP CHECK `chk_chat_public_source`")
    drop_new_columns = sql.index("DROP COLUMN `user_suppl_nutrient_id`")
    restore_patient = sql.index("ADD CONSTRAINT `chk_chat_patient_source`")
    restore_public = sql.index("ADD CONSTRAINT `chk_chat_public_source`")

    assert drop_patient < drop_new_columns < restore_patient
    assert drop_public < drop_new_columns < restore_public

    patient_check = sql[restore_patient : sql.index(";", restore_patient)]
    public_check = sql[restore_public : sql.index(";", restore_public)]

    assert "'PATIENT_SAVED_FIELD'" in patient_check
    assert "'PUBLIC_RAG_CHUNK'" in patient_check
    assert "'USER_SUPPLEMENT'" not in patient_check
    assert "'INTERACTION_RULE'" not in patient_check
    assert "'PATIENT_SAVED_FIELD'" in public_check
    assert "'PUBLIC_RAG_CHUNK'" in public_check
