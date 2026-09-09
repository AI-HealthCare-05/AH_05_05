"""Create a repeatable, local-only active-intake account for chat evaluation.

The script never creates or approves clinical ground truth.  It first checks
that reviewed interaction entities, therapeutic classification, supplement
mapping, and APPROVED interaction rules already exist.  ``--apply`` then adds
only a dedicated user, confirmed care episode, and active intake registrations.

Examples:

    # Read-only prerequisite report
    uv run python -m scripts.seed_chat_evaluation_account

    # Explicit local evaluation-account creation
    uv run python -m scripts.seed_chat_evaluation_account \
      --apply --email evaluation@example.com --password 'change-this-password'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tortoise import Tortoise
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.models.care import CareEpisode  # noqa: E402
from app.models.enums import (  # noqa: E402
    AccountStatus,
    CareEpisodeStatus,
    InteractionEntityKind,
    InteractionMatchMethod,
    InteractionReviewStatus,
    SupplementStatus,
)
from app.models.interactions import (  # noqa: E402
    InteractionEntity,
    InteractionEntityTherapeuticClass,
    InteractionRule,
    InteractionRuleSource,
    MedicationInteractionEntity,
    SupplementInteractionEntity,
    TherapeuticClass,
)
from app.models.medications import Medication  # noqa: E402
from app.models.supplement_nutrients import (  # noqa: E402
    SupplementNutrient,
    UserSupplementNutrient,
)
from app.models.users import User  # noqa: E402


class EvaluationSeedPrerequisiteError(ValueError):
    """Raised when the evaluation account would lack reviewed ground truth."""


@dataclass(frozen=True)
class EvaluationMedicationSpec:
    name: str
    entity_kind: InteractionEntityKind
    entity_name: str


@dataclass(frozen=True)
class EvaluationRuleSpec:
    left_entity_name: str
    right_entity_name: str


@dataclass(frozen=True)
class EvaluationSeedPlan:
    medications: tuple[EvaluationMedicationSpec, ...]
    supplement_name: str
    supplement_entity_name: str
    therapeutic_class_code: str
    interaction_rule_dataset_version: str
    therapeutic_class_dataset_version: str
    required_rules: tuple[EvaluationRuleSpec, ...]
    care_episode_alias: str = "AI Worker 평가 복약정보"


@dataclass(frozen=True)
class EvaluationSeedPrerequisites:
    missing: list[str]
    approved_rule_pair_keys: list[str]
    interaction_entity_ids: dict[str, int]
    supplement_nutrient_id: int | None
    therapeutic_class_id: int | None


@dataclass(frozen=True)
class EvaluationSeedResult:
    dry_run: bool
    prerequisites: EvaluationSeedPrerequisites
    user_id: int | None = None
    care_episode_id: int | None = None
    created_user_count: int = 0
    created_care_episode_count: int = 0
    created_medication_count: int = 0
    created_medication_mapping_count: int = 0
    created_supplement_registration_count: int = 0


def build_evaluation_seed_plan(
    *,
    interaction_rule_dataset_version: str = "interaction-pilot-v1",
    therapeutic_class_dataset_version: str = "therapeutic-class-v1",
) -> EvaluationSeedPlan:
    """Return the fixed evaluation scenario without reading or writing the DB."""

    return EvaluationSeedPlan(
        medications=(
            EvaluationMedicationSpec(
                name="케토롤락",
                entity_kind=InteractionEntityKind.DRUG,
                entity_name="케토롤락",
            ),
            EvaluationMedicationSpec(
                name="아스피린",
                entity_kind=InteractionEntityKind.DRUG,
                entity_name="아스피린",
            ),
            EvaluationMedicationSpec(
                name="와파린",
                entity_kind=InteractionEntityKind.DRUG,
                entity_name="와파린",
            ),
        ),
        supplement_name="비타민 K",
        supplement_entity_name="비타민 K",
        therapeutic_class_code="ANTICOAGULANT",
        interaction_rule_dataset_version=interaction_rule_dataset_version.strip(),
        therapeutic_class_dataset_version=therapeutic_class_dataset_version.strip(),
        required_rules=(
            EvaluationRuleSpec("케토롤락", "아스피린"),
            EvaluationRuleSpec("와파린", "비타민 K"),
        ),
    )


async def inspect_evaluation_seed_prerequisites(
    plan: EvaluationSeedPlan,
) -> EvaluationSeedPrerequisites:
    """Read reviewed data only; return all missing requirements in one report."""

    expected_entities = [
        *[(item.entity_kind, item.entity_name) for item in plan.medications],
        (InteractionEntityKind.SUPPLEMENT, plan.supplement_entity_name),
    ]
    entities: dict[str, InteractionEntity] = {}
    missing: list[str] = []
    for kind, canonical_name in expected_entities:
        entity = await InteractionEntity.filter(
            entity_kind=kind,
            normalized_name=_normalize_name(canonical_name),
        ).first()
        if entity is None:
            missing.append(f"상호작용 엔터티 없음: {kind.value}/{canonical_name}")
            continue
        entities[canonical_name] = entity

    supplement = await _find_registered_supplement(
        entities.get(plan.supplement_entity_name),
    )
    if supplement is None:
        missing.append(f"영양제 카탈로그 매핑 없음: {plan.supplement_name}")

    therapeutic_class = await TherapeuticClass.filter(
        code=plan.therapeutic_class_code,
    ).first()
    warfarin = entities.get("와파린")
    if therapeutic_class is None:
        missing.append(f"치료군 없음: {plan.therapeutic_class_code}")
    elif warfarin is None:
        missing.append("와파린 치료군 검증 불가: 상호작용 엔터티 없음")
    elif not await InteractionEntityTherapeuticClass.filter(
        interaction_entity_id=warfarin.id,
        therapeutic_class_id=therapeutic_class.id,
        review_status=InteractionReviewStatus.APPROVED,
        classification_dataset_version=plan.therapeutic_class_dataset_version,
    ).exists():
        missing.append(
            "승인된 와파린 항응고제 분류 없음: "
            f"{plan.therapeutic_class_dataset_version}"
        )

    approved_rule_pair_keys: list[str] = []
    for rule_spec in plan.required_rules:
        left = entities.get(rule_spec.left_entity_name)
        right = entities.get(rule_spec.right_entity_name)
        if left is None or right is None:
            continue
        rules = await InteractionRule.filter(
            Q(left_entity_id=left.id, right_entity_id=right.id)
            | Q(left_entity_id=right.id, right_entity_id=left.id),
            review_status=InteractionReviewStatus.APPROVED,
            rule_dataset_version=plan.interaction_rule_dataset_version,
        ).order_by("id")
        rules_with_sources = [
            rule
            for rule in rules
            if await InteractionRuleSource.filter(interaction_rule_id=rule.id).exists()
        ]
        if not rules_with_sources:
            missing.append(
                "출처가 있는 승인 상호작용 규칙 없음: "
                f"{rule_spec.left_entity_name}–{rule_spec.right_entity_name} "
                f"({plan.interaction_rule_dataset_version})"
            )
            continue
        approved_rule_pair_keys.extend(rule.pair_key for rule in rules_with_sources)

    return EvaluationSeedPrerequisites(
        missing=missing,
        approved_rule_pair_keys=list(dict.fromkeys(approved_rule_pair_keys)),
        interaction_entity_ids={name: entity.id for name, entity in entities.items()},
        supplement_nutrient_id=(supplement.id if supplement is not None else None),
        therapeutic_class_id=(therapeutic_class.id if therapeutic_class is not None else None),
    )


async def seed_evaluation_account(
    plan: EvaluationSeedPlan,
    *,
    apply: bool,
    email: str | None = None,
    password: str | None = None,
    today: date | None = None,
) -> EvaluationSeedResult:
    """Create the evaluation account only after reviewed prerequisites pass."""

    prerequisites = await inspect_evaluation_seed_prerequisites(plan)
    if prerequisites.missing:
        raise EvaluationSeedPrerequisiteError("\n".join(prerequisites.missing))
    if not apply:
        return EvaluationSeedResult(
            dry_run=True,
            prerequisites=prerequisites,
        )

    normalized_email = (email or "").strip().casefold()
    if not normalized_email or not password:
        raise ValueError("--apply에는 평가 계정 email과 password가 필요합니다.")
    current_date = today or date.today()
    required_entities = prerequisites.interaction_entity_ids
    supplement_nutrient_id = prerequisites.supplement_nutrient_id
    if supplement_nutrient_id is None:
        raise EvaluationSeedPrerequisiteError("영양제 카탈로그 매핑이 확인되지 않았습니다.")

    created_user_count = 0
    created_care_episode_count = 0
    created_medication_count = 0
    created_medication_mapping_count = 0
    created_supplement_registration_count = 0
    async with in_transaction() as connection:
        user, created_user_count = await _create_or_reuse_user(
            connection=connection,
            email=normalized_email,
            password=password,
        )
        episode, created_care_episode_count = await _create_or_reuse_episode(
            connection=connection,
            user_id=user.id,
            alias=plan.care_episode_alias,
            current_date=current_date,
        )

        for spec in plan.medications:
            medication, created = await _create_or_reuse_medication(
                connection=connection,
                care_episode_id=episode.id,
                name=spec.name,
                current_date=current_date,
            )
            created_medication_count += created

            entity_id = required_entities[spec.entity_name]
            created_medication_mapping_count += await _ensure_medication_mapping(
                connection=connection,
                medication_id=medication.id,
                interaction_entity_id=entity_id,
                matched_source_text=spec.name,
            )

        created_supplement_registration_count = await _create_or_reuse_supplement_registration(
            connection=connection,
            user_id=user.id,
            supplement_nutrient_id=supplement_nutrient_id,
            current_date=current_date,
        )

    return EvaluationSeedResult(
        dry_run=False,
        prerequisites=prerequisites,
        user_id=user.id,
        care_episode_id=episode.id,
        created_user_count=created_user_count,
        created_care_episode_count=created_care_episode_count,
        created_medication_count=created_medication_count,
        created_medication_mapping_count=created_medication_mapping_count,
        created_supplement_registration_count=created_supplement_registration_count,
    )


async def _create_or_reuse_user(
    *,
    connection: Any,
    email: str,
    password: str,
) -> tuple[User, int]:
    user = await User.filter(email=email).using_db(connection).first()
    if user is not None:
        return user, 0
    return (
        await User.create(
            email=email,
            hashed_password=hash_password(password),
            status=AccountStatus.ACTIVE,
            name="AI Worker 평가 계정",
            using_db=connection,
        ),
        1,
    )


async def _create_or_reuse_episode(
    *,
    connection: Any,
    user_id: int,
    alias: str,
    current_date: date,
) -> tuple[CareEpisode, int]:
    episode = await CareEpisode.filter(
        user_id=user_id,
        alias=alias,
    ).using_db(connection).first()
    if episode is not None:
        return episode, 0
    return (
        await CareEpisode.create(
            user_id=user_id,
            alias=alias,
            status=CareEpisodeStatus.ACTIVE,
            confirmation_hash="e" * 64,
            confirmed_at=datetime.combine(current_date, datetime.min.time()),
            medication_start_date=current_date,
            using_db=connection,
        ),
        1,
    )


async def _create_or_reuse_medication(
    *,
    connection: Any,
    care_episode_id: int,
    name: str,
    current_date: date,
) -> tuple[Medication, int]:
    medication = await Medication.filter(
        care_episode_id=care_episode_id,
        name=name,
    ).using_db(connection).first()
    if medication is not None:
        return medication, 0
    return (
        await Medication.create(
            care_episode_id=care_episode_id,
            name=name,
            dose_quantity="1정",
            times_per_day=1,
            days=30,
            prescribed_at=current_date,
            using_db=connection,
        ),
        1,
    )


async def _ensure_medication_mapping(
    *,
    connection: Any,
    medication_id: int,
    interaction_entity_id: int,
    matched_source_text: str,
) -> int:
    mapping_exists = await MedicationInteractionEntity.filter(
        medication_id=medication_id,
        interaction_entity_id=interaction_entity_id,
    ).using_db(connection).exists()
    if mapping_exists:
        return 0
    await MedicationInteractionEntity.create(
        medication_id=medication_id,
        interaction_entity_id=interaction_entity_id,
        match_method=InteractionMatchMethod.EXACT_NAME,
        matched_source_text=matched_source_text,
        using_db=connection,
    )
    return 1


async def _create_or_reuse_supplement_registration(
    *,
    connection: Any,
    user_id: int,
    supplement_nutrient_id: int,
    current_date: date,
) -> int:
    registration = await UserSupplementNutrient.filter(
        user_id=user_id,
        supplement_nutrient_id=supplement_nutrient_id,
    ).using_db(connection).first()
    if registration is not None:
        return 0
    await UserSupplementNutrient.create(
        user_id=user_id,
        supplement_nutrient_id=supplement_nutrient_id,
        dose_amount="1",
        dose_unit="정",
        start_date=current_date,
        status=SupplementStatus.ACTIVE,
        using_db=connection,
    )
    return 1


async def _find_registered_supplement(
    supplement_entity: InteractionEntity | None,
) -> SupplementNutrient | None:
    if supplement_entity is None:
        return None
    mapping = await SupplementInteractionEntity.filter(
        interaction_entity_id=supplement_entity.id,
    ).order_by("supplement_nutrient_id").first()
    if mapping is None:
        return None
    return await SupplementNutrient.get_or_none(id=mapping.supplement_nutrient_id)


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="평가 계정과 복약정보를 실제로 생성합니다.")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--interaction-rule-dataset-version", default="interaction-pilot-v1")
    parser.add_argument("--therapeutic-class-dataset-version", default="therapeutic-class-v1")
    args = parser.parse_args(argv)
    if args.apply and (not args.email or not args.password):
        parser.error("--apply에는 --email과 --password가 필요합니다.")
    return args


async def _run(args: argparse.Namespace) -> EvaluationSeedResult:
    plan = build_evaluation_seed_plan(
        interaction_rule_dataset_version=args.interaction_rule_dataset_version,
        therapeutic_class_dataset_version=args.therapeutic_class_dataset_version,
    )
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await seed_evaluation_account(
            plan,
            apply=args.apply,
            email=args.email,
            password=args.password,
        )
    finally:
        await Tortoise.close_connections()


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(_run(args))
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
