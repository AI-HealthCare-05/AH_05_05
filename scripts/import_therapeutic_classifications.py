from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_worker.schemas.interaction import InteractionEntityKind, normalize_interaction_name  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.enums import InteractionReviewStatus  # noqa: E402
from app.models.interactions import (  # noqa: E402
    InteractionEntity,
    InteractionEntityTherapeuticClass,
    TherapeuticClass,
    TherapeuticClassAlias,
)


class TherapeuticClassificationImportError(ValueError):
    pass


class TherapeuticClassAssignmentDatasetRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_kind: InteractionEntityKind
    canonical_name: str = Field(min_length=1)
    review_status: InteractionReviewStatus
    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    raw_classification_text: str = Field(min_length=1)
    source_url: str | None = None
    approved_at: datetime | None = None

    @field_validator(
        "canonical_name",
        "source_id",
        "document_id",
        "record_id",
        "raw_classification_text",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("필수 텍스트는 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def require_approval_time_for_approved_assignment(self) -> TherapeuticClassAssignmentDatasetRow:
        if self.review_status == InteractionReviewStatus.APPROVED and self.approved_at is None:
            raise ValueError("APPROVED 치료군 분류에는 approved_at이 필요합니다.")
        if self.review_status != InteractionReviewStatus.APPROVED and self.approved_at is not None:
            raise ValueError("APPROVED가 아닌 치료군 분류에는 approved_at을 지정할 수 없습니다.")
        return self


class TherapeuticClassDatasetRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    aliases: list[str] = Field(min_length=1)
    assignments: list[TherapeuticClassAssignmentDatasetRow] = Field(min_length=1)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("치료군 코드는 비어 있을 수 없습니다.")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("치료군 표시는 비어 있을 수 없습니다.")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            alias = normalize_interaction_name(value)
            if not alias:
                raise ValueError("치료군 별칭은 비어 있을 수 없습니다.")
            if alias not in normalized:
                normalized.append(alias)
        return normalized


class TherapeuticClassificationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["therapeutic-classification-dataset-v1"]
    dataset_version: str = Field(min_length=1)
    classes: list[TherapeuticClassDatasetRow] = Field(min_length=1)

    @field_validator("dataset_version")
    @classmethod
    def normalize_dataset_version(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("dataset_version은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def require_unique_class_codes(self) -> TherapeuticClassificationDataset:
        codes = [item.code for item in self.classes]
        if len(codes) != len(set(codes)):
            raise ValueError("치료군 code는 중복될 수 없습니다.")
        return self


@dataclass(frozen=True)
class TherapeuticClassificationImportResult:
    dataset_version: str
    class_count: int
    alias_count: int
    assignment_count: int
    approved_assignment_count: int


def load_therapeutic_classification_dataset(path: Path) -> TherapeuticClassificationDataset:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TherapeuticClassificationDataset.model_validate(raw)


async def import_therapeutic_classification_dataset(
    dataset: TherapeuticClassificationDataset,
) -> dict[str, int | str]:
    alias_count = 0
    assignment_count = 0
    approved_assignment_count = 0
    async with in_transaction() as connection:
        for class_row in dataset.classes:
            therapeutic_class, _ = await TherapeuticClass.update_or_create(
                code=class_row.code,
                defaults={"display_name": class_row.display_name},
                using_db=connection,
            )
            for alias in class_row.aliases:
                _, created = await TherapeuticClassAlias.get_or_create(
                    therapeutic_class=therapeutic_class,
                    normalized_alias=normalize_interaction_name(alias).casefold(),
                    defaults={"alias": alias},
                    using_db=connection,
                )
                alias_count += int(created)
            for assignment in class_row.assignments:
                entity = await InteractionEntity.get_or_none(
                    entity_kind=assignment.entity_kind,
                    normalized_name=normalize_interaction_name(assignment.canonical_name).casefold(),
                ).using_db(connection)
                if entity is None:
                    raise TherapeuticClassificationImportError(
                        "기존 interaction_entity가 없어 치료군 분류를 적재할 수 없습니다: "
                        f"{assignment.entity_kind.value}:{assignment.canonical_name}"
                    )
                _, created = await InteractionEntityTherapeuticClass.update_or_create(
                    interaction_entity=entity,
                    therapeutic_class=therapeutic_class,
                    classification_dataset_version=dataset.dataset_version,
                    defaults={
                        "review_status": assignment.review_status,
                        "source_id": assignment.source_id,
                        "document_id": assignment.document_id,
                        "record_id": assignment.record_id,
                        "raw_classification_text": assignment.raw_classification_text,
                        "source_url": assignment.source_url,
                        "approved_at": assignment.approved_at,
                    },
                    using_db=connection,
                )
                assignment_count += int(created)
                approved_assignment_count += int(assignment.review_status == InteractionReviewStatus.APPROVED)
    return asdict(
        TherapeuticClassificationImportResult(
            dataset_version=dataset.dataset_version,
            class_count=len(dataset.classes),
            alias_count=alias_count,
            assignment_count=assignment_count,
            approved_assignment_count=approved_assignment_count,
        )
    )


async def _run(path: Path) -> dict[str, int | str]:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await import_therapeutic_classification_dataset(
            load_therapeutic_classification_dataset(path),
        )
    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(description="검수된 치료군 분류 데이터셋을 적재합니다.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "data/knowledge/manifests/therapeutic_classifications.yaml",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.dataset)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
