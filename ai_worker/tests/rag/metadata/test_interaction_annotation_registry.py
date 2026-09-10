from pathlib import Path

import pytest

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.metadata.knowledge_entity_extractor import KnowledgeEntityExtractor
from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
)
from ai_worker.schemas.knowledge import KnowledgeDocumentType


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
    assert matches[0].food_names == ["과일주스"]
    assert matches[0].entity_catalog_entries[1].canonical_name == "과일주스"
    assert matches[0].entity_catalog_entries[1].aliases == [
        "과일주스",
        "자몽주스",
        "오렌지주스",
        "사과주스",
    ]
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


def test_requires_a_reviewed_evidence_phrase_when_configured(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "annotations.yaml"
    manifest_path.write_text(
        """
schema_version: knowledge-interaction-annotations-v1
documents:
  - document_id: reviewed-paper
    pairs:
      - pair_type: SUPPLEMENT_SUPPLEMENT
        evidence_phrases: ["reduced zinc absorption by iron"]
        left:
          kind: SUPPLEMENT
          display_name: 철분
          aliases: [iron]
        right:
          kind: SUPPLEMENT
          display_name: 아연
          aliases: [zinc]
""".strip(),
        encoding="utf-8",
    )
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(manifest_path)

    assert (
        registry.find_matches(
            document_id="reviewed-paper",
            text="Iron and zinc are mentioned elsewhere in the review.",
        )
        == []
    )
    assert (
        len(
            registry.find_matches(
                document_id="reviewed-paper",
                text="Supplemental iron reduced zinc absorption by iron in a dose-dependent way.",
            )
        )
        == 1
    )


def test_source_backed_calcium_iron_annotation_uses_only_its_review_document() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )

    matches = registry.find_matches(
        document_id="research_supplement_interactions-016c81c9a3e29ebd",
        text="This review discusses calcium intake and iron absorption.",
    )

    assert len(matches) == 1
    assert matches[0].pair_type == InteractionPairType.SUPPLEMENT_SUPPLEMENT
    assert matches[0].ingredient_names == ["칼슘", "철분"]
    assert matches[0].food_names == []


def test_source_backed_vitamin_d_calcium_annotation_requires_both_official_source_entities() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )

    matches = registry.find_matches(
        document_id="mfds_supplement_code-72e61399c742b0e5",
        text="비타민 D는 칼슘과 인이 흡수되고 이용되는데 필요합니다.",
    )

    assert len(matches) == 1
    assert matches[0].pair_type == InteractionPairType.SUPPLEMENT_SUPPLEMENT
    assert matches[0].ingredient_names == ["비타민 D", "칼슘"]
    assert (
        registry.find_matches(
            document_id="mfds_supplement_code-72e61399c742b0e5",
            text="비타민 D의 일일섭취량은 3~10 μg입니다.",
        )
        == []
    )


def test_does_not_add_magnesium_zinc_pair_without_a_reviewed_source_annotation() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )

    assert (
        registry.find_matches(
            document_id="mfds_supplement_code-0d785fd735e66685",
            text="마그네슘과 아연을 함께 언급한 일반 성분 안내입니다.",
        )
        == []
    )
    magnesium_zinc_pair_key = build_interaction_pair_key(
        InteractionEntity(
            kind=InteractionEntityKind.SUPPLEMENT,
            display_name="마그네슘",
        ),
        InteractionEntity(
            kind=InteractionEntityKind.SUPPLEMENT,
            display_name="아연",
        ),
    )
    assert magnesium_zinc_pair_key not in registry.required_pair_keys()


def test_source_backed_micronutrient_review_matches_only_reviewed_direct_pairs() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )
    document_id = "research_micronutrient_interactions-e3b164ce9cc98cc6"

    assert registry.find_matches(
        document_id=document_id,
        text="An absorption-depressing effect of calcium on iron absorption was observed.",
    )[0].ingredient_names == ["칼슘", "철분"]
    assert registry.find_matches(
        document_id=document_id,
        text="The absorption of zinc was reduced by iron in a dose-dependent way.",
    )[0].ingredient_names == ["철분", "아연"]
    assert registry.find_matches(
        document_id=document_id,
        text="Zinc-copper-iron interactions were observed at high supplemental doses.",
    )[0].ingredient_names == ["아연", "구리"]
    assert registry.find_matches(
        document_id=document_id,
        text="Vitamin C is a strong promoter of iron absorption from the diet.",
    )[0].ingredient_names == ["비타민 C", "철분"]
    assert (
        registry.find_matches(
            document_id=document_id,
            text="Magnesium and zinc are both essential minerals.",
        )
        == []
    )


def test_reviewed_document_does_not_fallback_to_a_pair_inferred_only_from_heading() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )

    entities = KnowledgeEntityExtractor(
        interaction_annotations=registry,
    ).extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Micronutrient interactions: effects on absorption and bioavailability",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
        content="Iron-zinc interactions are a topic in this review.",
    )

    assert entities.interaction_pair_keys == []


def test_source_backed_acetaminophen_alcohol_annotation_exposes_food_aliases() -> None:
    repo_root = Path(__file__).parents[4]
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / "data/knowledge/manifests/interaction_annotations.yaml",
    )

    matches = registry.find_matches(
        document_id="kpicia_pharm_review-3ce7212b15e7c2de",
        text="아세트아미노펜은 알코올과의 상호작용으로 간손상을 초래할 수 있습니다.",
    )

    assert len(matches) == 1
    assert matches[0].pair_type == InteractionPairType.DRUG_FOOD
    assert matches[0].drug_names == ["아세트아미노펜"]
    assert matches[0].food_names == ["알코올"]
    assert matches[0].entity_catalog_entries[1].aliases == [
        "알코올",
        "술",
        "음주",
        "alcohol",
    ]


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
