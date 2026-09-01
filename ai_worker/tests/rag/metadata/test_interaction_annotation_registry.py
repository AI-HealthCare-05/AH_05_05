from pathlib import Path

import pytest

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.schemas.interaction import InteractionPairType


def test_loads_document_scoped_pair_and_matches_both_entities(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
schema_version: knowledge-interaction-annotations-v1
documents:
  - document_id: mfds-guide
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [펙소페나딘, fexofenadine]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스, 자몽주스, 오렌지주스, 사과주스]
""".strip(),
        encoding="utf-8",
    )
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)

    matches = registry.find_matches(
        document_id="mfds-guide",
        text="펙소페나딘은 자몽주스 대신 물과 함께 복용합니다.",
    )

    assert len(matches) == 1
    assert matches[0].pair_type == InteractionPairType.DRUG_FOOD
    assert matches[0].drug_names == ["펙소페나딘"]
    assert matches[0].ingredient_names == []
    assert len(matches[0].interaction_pair_keys) == 1
    assert registry.required_pair_keys() == matches[0].interaction_pair_keys


def test_does_not_apply_document_annotation_when_one_entity_is_absent(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
schema_version: knowledge-interaction-annotations-v1
documents:
  - document_id: mfds-guide
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [펙소페나딘]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스]
""".strip(),
        encoding="utf-8",
    )
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)

    matches = registry.find_matches(
        document_id="mfds-guide",
        text="펙소페나딘은 2세대 항히스타민제입니다.",
    )

    assert matches == []


def test_rejects_blank_alias_that_would_match_every_chunk(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
documents:
  - document_id: mfds-guide
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [" "]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="별칭"):
        KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
schema_version: knowledge-interaction-annotations-v2
documents: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)


def test_rejects_duplicate_document_annotations(tmp_path: Path) -> None:
    document = """
  - document_id: duplicated-document
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [펙소페나딘]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스]
"""
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        f"schema_version: knowledge-interaction-annotations-v1\ndocuments:\n{document}{document}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="document_id"):
        KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)


def test_rejects_pair_type_that_disagrees_with_entity_kinds(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
documents:
  - document_id: invalid-pair
    pairs:
      - pair_type: DRUG_DRUG
        left:
          kind: DRUG
          display_name: 와파린
          aliases: [와파린]
        right:
          kind: SUPPLEMENT
          display_name: 비타민 K
          aliases: [비타민 K]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pair_type"):
        KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)
