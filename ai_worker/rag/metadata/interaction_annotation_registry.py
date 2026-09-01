import re
import unicodedata
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
    interaction_pair_type_for_kinds,
    normalize_interaction_name,
)


class KnowledgeInteractionAnnotationEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: InteractionEntityKind
    display_name: str = Field(min_length=1)
    aliases: list[str] = Field(min_length=1)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("상호작용 주체 이름은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        aliases: list[str] = []
        for value in values:
            normalized = normalize_interaction_name(value)
            if not normalized:
                raise ValueError("상호작용 별칭은 비어 있을 수 없습니다.")
            if normalized not in aliases:
                aliases.append(normalized)
        return aliases


class KnowledgeInteractionAnnotationPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_type: InteractionPairType
    left: KnowledgeInteractionAnnotationEntity
    right: KnowledgeInteractionAnnotationEntity

    @model_validator(mode="after")
    def validate_pair_type(self) -> Self:
        expected = interaction_pair_type_for_kinds(
            self.left.kind,
            self.right.kind,
        )
        if expected != self.pair_type:
            raise ValueError("pair_type이 주석의 상호작용 주체 종류와 일치하지 않습니다.")
        return self


class KnowledgeInteractionDocumentAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    pairs: list[KnowledgeInteractionAnnotationPair] = Field(min_length=1)

    @field_validator("document_id")
    @classmethod
    def normalize_document_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("document_id는 비어 있을 수 없습니다.")
        return normalized


class KnowledgeInteractionAnnotationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["knowledge-interaction-annotations-v1"] = "knowledge-interaction-annotations-v1"
    documents: list[KnowledgeInteractionDocumentAnnotation] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_document_ids(self) -> Self:
        document_ids = [document.document_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("주석 documents의 document_id는 중복될 수 없습니다.")
        return self


class MatchedKnowledgeInteraction(BaseModel):
    pair_type: InteractionPairType
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    interaction_pair_keys: list[str] = Field(default_factory=list)


class KnowledgeInteractionAnnotationRegistry:
    """사람이 검수한 문서별 상호작용 조합만 청크 메타데이터로 확정합니다."""

    def __init__(
        self,
        manifest: KnowledgeInteractionAnnotationManifest,
    ) -> None:
        self._pairs_by_document = {document.document_id: document.pairs for document in manifest.documents}

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(KnowledgeInteractionAnnotationManifest.model_validate(raw))

    def required_pair_keys(self) -> list[str]:
        return sorted(
            {pair_key for pair_keys in self.required_pair_keys_by_document().values() for pair_key in pair_keys}
        )

    def required_pair_keys_by_document(self) -> dict[str, list[str]]:
        return {
            document_id: sorted({self._pair_key(pair) for pair in pairs})
            for document_id, pairs in self._pairs_by_document.items()
        }

    @staticmethod
    def _pair_key(
        pair: KnowledgeInteractionAnnotationPair,
    ) -> str:
        return build_interaction_pair_key(
            InteractionEntity(
                kind=pair.left.kind,
                display_name=pair.left.display_name,
            ),
            InteractionEntity(
                kind=pair.right.kind,
                display_name=pair.right.display_name,
            ),
        )

    def find_matches(
        self,
        *,
        document_id: str,
        text: str,
    ) -> list[MatchedKnowledgeInteraction]:
        pairs = self._pairs_by_document.get(document_id)
        if not pairs:
            return []

        normalized_text = self._normalize_for_match(text)
        matches: list[MatchedKnowledgeInteraction] = []
        for pair in pairs:
            if not self._matches_entity(normalized_text, pair.left):
                continue
            if not self._matches_entity(normalized_text, pair.right):
                continue

            left = InteractionEntity(
                kind=pair.left.kind,
                display_name=pair.left.display_name,
            )
            right = InteractionEntity(
                kind=pair.right.kind,
                display_name=pair.right.display_name,
            )
            entities = (pair.left, pair.right)
            matches.append(
                MatchedKnowledgeInteraction(
                    pair_type=pair.pair_type,
                    drug_names=[
                        entity.display_name for entity in entities if entity.kind == InteractionEntityKind.DRUG
                    ],
                    ingredient_names=[
                        entity.display_name for entity in entities if entity.kind == InteractionEntityKind.SUPPLEMENT
                    ],
                    interaction_pair_keys=[build_interaction_pair_key(left, right)],
                )
            )
        return matches

    @classmethod
    def _matches_entity(
        cls,
        normalized_text: str,
        entity: KnowledgeInteractionAnnotationEntity,
    ) -> bool:
        aliases = [entity.display_name, *entity.aliases]
        return any(cls._normalize_for_match(alias) in normalized_text for alias in aliases)

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
