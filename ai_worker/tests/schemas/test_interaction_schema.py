import pytest
from pydantic import ValidationError

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    InteractionReviewStatus,
    InteractionRiskLevel,
    InteractionRuleCandidate,
    InteractionSourceRecord,
)


def build_drug(
    name: str,
    *,
    source_code: str,
) -> InteractionEntity:
    return InteractionEntity(
        kind=InteractionEntityKind.DRUG,
        display_name=name,
        source_code=source_code,
    )


def build_source(record_id: str = "23") -> InteractionSourceRecord:
    return InteractionSourceRecord(
        source_id="mfds_drug_records",
        document_id="mfds-dur-contraindication",
        record_id=record_id,
    )


def test_entity_normalizes_unicode_whitespace_and_case() -> None:
    entity = InteractionEntity(
        kind=InteractionEntityKind.SUPPLEMENT,
        display_name="  Vitamin   Ｃ  ",
    )

    assert entity.display_name == "Vitamin C"
    assert entity.normalized_name == "vitamin c"


def test_candidate_pair_key_is_independent_of_input_order() -> None:
    paroxetine = build_drug("파록세틴", source_code="D000353")
    selegiline = build_drug("셀레길린염산염", source_code="D000139")

    first = InteractionRuleCandidate(
        dataset_version="interaction-pilot-v1",
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=paroxetine,
        right_entity=selegiline,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        effect_summaries=["세로토닌성증후군"],
        source_records=[build_source()],
    )
    reversed_pair = InteractionRuleCandidate(
        dataset_version="interaction-pilot-v1",
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=selegiline,
        right_entity=paroxetine,
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        effect_summaries=["세로토닌성증후군"],
        source_records=[build_source()],
    )

    assert first.pair_key == reversed_pair.pair_key
    assert first.candidate_id == reversed_pair.candidate_id
    assert first.left_entity.normalized_name == "파록세틴"
    assert first.right_entity.normalized_name == "셀레길린염산염"


def test_candidate_normalizes_duplicate_effects_sources_and_chunks() -> None:
    candidate = InteractionRuleCandidate(
        dataset_version="interaction-pilot-v1",
        pair_type=InteractionPairType.DRUG_DRUG,
        left_entity=build_drug("아토르바스타틴", source_code="D000455"),
        right_entity=build_drug("케토코나졸", source_code="D000769"),
        risk_level=InteractionRiskLevel.CONTRAINDICATED,
        effect_summaries=[" 근육병증 ", "근육병증"],
        source_records=[build_source("29"), build_source("29")],
        evidence_chunk_ids=["a" * 64, "a" * 64],
    )

    assert candidate.effect_summaries == ["근육병증"]
    assert candidate.source_records == [build_source("29")]
    assert candidate.evidence_chunk_ids == ["a" * 64]


def test_automatic_candidate_cannot_be_preapproved() -> None:
    with pytest.raises(ValidationError, match="PENDING"):
        InteractionRuleCandidate(
            dataset_version="interaction-pilot-v1",
            pair_type=InteractionPairType.DRUG_DRUG,
            left_entity=build_drug("파록세틴", source_code="D000353"),
            right_entity=build_drug("셀레길린염산염", source_code="D000139"),
            risk_level=InteractionRiskLevel.CONTRAINDICATED,
            effect_summaries=["세로토닌성증후군"],
            source_records=[build_source()],
            review_status=InteractionReviewStatus.APPROVED,
        )


def test_candidate_rejects_pair_type_that_does_not_match_entities() -> None:
    with pytest.raises(ValidationError, match="pair_type"):
        InteractionRuleCandidate(
            dataset_version="interaction-pilot-v1",
            pair_type=InteractionPairType.DRUG_SUPPLEMENT,
            left_entity=build_drug("파록세틴", source_code="D000353"),
            right_entity=build_drug("셀레길린염산염", source_code="D000139"),
            risk_level=InteractionRiskLevel.CONTRAINDICATED,
            effect_summaries=["세로토닌성증후군"],
            source_records=[build_source()],
        )

