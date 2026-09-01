from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import (
    InteractionAliasType,
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionMappingStatus,
    InteractionMatchMethod,
    InteractionPairType,
    InteractionReviewStatus,
    InteractionRiskLevel,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)


class MedicationProductGuide(models.Model):
    id = fields.BigIntField(primary_key=True)
    item_seq = fields.CharField(max_length=20, unique=True)
    product_name = fields.CharField(max_length=255)
    manufacturer_name = fields.CharField(max_length=255)
    efficacy = fields.TextField()
    usage_instructions = fields.TextField()
    pre_use_warning = fields.TextField()
    precautions = fields.TextField()
    drug_food_interactions = fields.TextField()
    adverse_reactions = fields.TextField()
    storage_instructions = fields.TextField()
    item_image_url = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "medication_product_guides"
        indexes = (("product_name",),)


class InteractionEntity(models.Model):
    id = fields.BigIntField(primary_key=True)
    entity_kind = fields.CharEnumField(InteractionEntityKind)
    canonical_name = fields.CharField(max_length=255)
    normalized_name = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "interaction_entities"
        unique_together = (("entity_kind", "normalized_name"),)
        indexes = (("canonical_name",),)


class InteractionEntityAlias(models.Model):
    id = fields.BigIntField(primary_key=True)
    interaction_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="aliases",
        on_delete=fields.CASCADE,
    )
    alias_type = fields.CharEnumField(InteractionAliasType)
    alias = fields.CharField(max_length=255)
    normalized_alias = fields.CharField(max_length=255)
    is_preferred = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "interaction_entity_aliases"
        unique_together = (("interaction_entity", "normalized_alias"),)
        indexes = (("normalized_alias",),)


class InteractionEntityIdentifier(models.Model):
    id = fields.BigIntField(primary_key=True)
    interaction_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="identifiers",
        on_delete=fields.CASCADE,
    )
    source_id = fields.CharField(max_length=100)
    source_code = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "interaction_entity_identifiers"
        unique_together = (("source_id", "source_code"),)


class MedicationInteractionMapping(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication = fields.OneToOneField(
        "models.Medication",
        related_name="interaction_mapping",
        on_delete=fields.CASCADE,
    )
    mapping_status = fields.CharEnumField(
        InteractionMappingStatus,
        default=InteractionMappingStatus.PENDING,
    )
    error_code = fields.CharField(max_length=100, null=True)
    mapped_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "medication_interaction_mappings"
        indexes = (("mapping_status",),)


class MedicationInteractionEntity(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication = fields.ForeignKeyField(
        "models.Medication",
        related_name="interaction_entities",
        on_delete=fields.CASCADE,
    )
    interaction_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="medication_mappings",
        on_delete=fields.RESTRICT,
    )
    match_method = fields.CharEnumField(InteractionMatchMethod)
    match_confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("1")),
        ],
    )
    matched_source_text = fields.CharField(max_length=255)
    reviewed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_interaction_entities"
        unique_together = (("medication", "interaction_entity"),)
        indexes = (("interaction_entity",),)


class SupplementInteractionEntity(models.Model):
    id = fields.BigIntField(primary_key=True)
    supplement_nutrient = fields.ForeignKeyField(
        "models.SupplementNutrient",
        related_name="interaction_entities",
        on_delete=fields.CASCADE,
    )
    interaction_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="supplement_mappings",
        on_delete=fields.RESTRICT,
    )
    amount = fields.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit = fields.CharField(max_length=30, null=True)
    source_field = fields.CharField(max_length=100, null=True)
    match_method = fields.CharEnumField(
        InteractionMatchMethod,
        default=InteractionMatchMethod.SOURCE_CODE,
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "supplement_interaction_entities"
        unique_together = (("supplement_nutrient", "interaction_entity"),)
        indexes = (("interaction_entity",),)


class InteractionRule(models.Model):
    id = fields.BigIntField(primary_key=True)
    pair_key = fields.CharField(max_length=64)
    pair_type = fields.CharEnumField(InteractionPairType)
    left_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="left_rules",
        on_delete=fields.RESTRICT,
    )
    right_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="right_rules",
        on_delete=fields.RESTRICT,
    )
    risk_level = fields.CharEnumField(InteractionRiskLevel)
    review_status = fields.CharEnumField(
        InteractionReviewStatus,
        default=InteractionReviewStatus.PENDING,
    )
    rule_dataset_version = fields.CharField(max_length=100)
    extraction_method = fields.CharEnumField(InteractionExtractionMethod)
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "interaction_rules"
        unique_together = (("pair_key", "rule_dataset_version"),)
        indexes = (
            ("left_entity", "right_entity"),
            ("pair_type", "review_status", "risk_level"),
            ("rule_dataset_version",),
        )


class InteractionRuleSource(models.Model):
    id = fields.BigIntField(primary_key=True)
    interaction_rule = fields.ForeignKeyField(
        "models.InteractionRule",
        related_name="sources",
        on_delete=fields.CASCADE,
    )
    source_id = fields.CharField(max_length=100)
    document_id = fields.CharField(max_length=150)
    record_id = fields.CharField(max_length=150)
    raw_effect_text = fields.TextField()
    source_published_at = fields.DateField(null=True)
    source_url = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "interaction_rule_sources"
        unique_together = (("interaction_rule", "source_id", "document_id", "record_id"),)
        indexes = (("source_id", "record_id"),)


class InteractionRuleEvidenceChunk(models.Model):
    id = fields.BigIntField(primary_key=True)
    interaction_rule_source = fields.ForeignKeyField(
        "models.InteractionRuleSource",
        related_name="evidence_chunks",
        on_delete=fields.CASCADE,
    )
    dataset_key = fields.CharField(max_length=100)
    dataset_version = fields.CharField(max_length=100)
    vector_chunk_id = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "interaction_rule_evidence_chunks"
        unique_together = (("interaction_rule_source", "dataset_version", "vector_chunk_id"),)
        indexes = (("vector_chunk_id",),)


class MedicationSafetyRule(models.Model):
    id = fields.BigIntField(primary_key=True)
    rule_key = fields.CharField(max_length=64)
    interaction_entity = fields.ForeignKeyField(
        "models.InteractionEntity",
        related_name="medication_safety_rules",
        on_delete=fields.RESTRICT,
    )
    rule_type = fields.CharEnumField(MedicationSafetyRuleType)
    risk_level = fields.CharEnumField(InteractionRiskLevel)
    guidance_text = fields.TextField()
    review_status = fields.CharEnumField(
        InteractionReviewStatus,
        default=InteractionReviewStatus.PENDING,
    )
    rule_dataset_version = fields.CharField(max_length=100)
    extraction_method = fields.CharEnumField(InteractionExtractionMethod)
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "medication_safety_rules"
        unique_together = (("rule_key", "rule_dataset_version"),)
        indexes = (
            ("interaction_entity", "rule_type", "review_status"),
            ("rule_dataset_version", "review_status"),
        )


class MedicationSafetyRuleCondition(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication_safety_rule = fields.ForeignKeyField(
        "models.MedicationSafetyRule",
        related_name="conditions",
        on_delete=fields.CASCADE,
    )
    condition_group_no = fields.SmallIntField(
        validators=[MinValueValidator(1)],
    )
    condition_order = fields.SmallIntField(
        validators=[MinValueValidator(1)],
    )
    condition_kind = fields.CharEnumField(SafetyConditionKind)
    comparison_operator = fields.CharEnumField(SafetyComparisonOperator)
    value_min = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
    )
    value_max = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
    )
    value_text = fields.CharField(max_length=255, null=True)
    unit = fields.CharField(max_length=30, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_safety_rule_conditions"
        unique_together = (
            (
                "medication_safety_rule",
                "condition_group_no",
                "condition_order",
            ),
        )
        indexes = (("condition_kind", "comparison_operator"),)


class MedicationSafetyRuleSource(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication_safety_rule = fields.ForeignKeyField(
        "models.MedicationSafetyRule",
        related_name="sources",
        on_delete=fields.CASCADE,
    )
    source_id = fields.CharField(max_length=100)
    document_id = fields.CharField(max_length=150)
    record_id = fields.CharField(max_length=150)
    raw_effect_text = fields.TextField()
    source_published_at = fields.DateField(null=True)
    source_url = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_safety_rule_sources"
        unique_together = (
            (
                "medication_safety_rule",
                "source_id",
                "document_id",
                "record_id",
            ),
        )
        indexes = (("source_id", "record_id"),)
