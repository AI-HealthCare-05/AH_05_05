import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from tortoise.timezone import now

from ai_worker.domain.errors import (
    PatientContextNotFoundError,
    UnconfirmedPatientContextError,
)
from ai_worker.schemas.interaction import normalize_interaction_name
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    SupplementNutrientAmount,
)
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, SupplementStatus
from app.models.interactions import InteractionEntity, MedicationInteractionEntity
from app.models.medications import Medication
from app.models.supplement_nutrients import UserSupplementNutrient


def _service_today() -> date:
    return now().date()


class DbActiveIntakeContextProvider:
    _TRAILING_STRENGTH = re.compile(
        r"(?:(?<=\S)\s+|(?<=[가-힣]))\d+(?:\.\d+)?\s*"
        r"(?:mg|mcg|μg|㎍|g|밀리그램|마이크로그램|그램)\s*$",
        re.IGNORECASE,
    )
    _TRAILING_GENERIC_DOSAGE_FORM = re.compile(r"(?:정|캡슐)$")
    _COMBINATION_SEPARATOR = re.compile(r"[/+,&·ㆍ]")

    def __init__(
        self,
        *,
        today_provider: Callable[[], date] = _service_today,
        include_all_episode_medications: bool = False,
    ) -> None:
        self._today_provider = today_provider
        self._include_all_episode_medications = include_all_episode_medications

    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext:
        if care_episode_id is not None:
            await self._validate_preferred_episode(
                user_id=user_id,
                care_episode_id=care_episode_id,
            )

        episodes = await CareEpisode.filter(
            user_id=user_id,
            status=CareEpisodeStatus.ACTIVE,
            confirmed_at__not_isnull=True,
        )
        episodes_by_id = {episode.id: episode for episode in episodes}
        medication_rows = (
            await Medication.filter(
                care_episode_id__in=episodes_by_id,
            )
            .prefetch_related("slots")
            .order_by("id")
        )
        supplement_rows = await UserSupplementNutrient.filter(
            user_id=user_id,
            status=SupplementStatus.ACTIVE,
            supplement_nutrient_id__isnull=False,
        ).prefetch_related("supplement_nutrient", "slots")

        today = self._today_provider()
        medications = [
            self._to_active_medication(row)
            for row in medication_rows
            if self._include_all_episode_medications
            or self._is_current_medication(
                row,
                episode=episodes_by_id[row.care_episode_id],
                today=today,
            )
        ]
        medications = await self._with_interaction_names(medications)
        supplements = [
            self._to_active_supplement(row)
            for row in supplement_rows
            if row.start_date <= today and (row.end_date is None or row.end_date >= today)
        ]

        return ActiveIntakeContext(
            user_id=user_id,
            preferred_care_episode_id=care_episode_id,
            medications=medications,
            supplements=supplements,
        )

    @classmethod
    async def _with_interaction_names(cls, medications: list[ActiveMedication]) -> list[ActiveMedication]:
        if not medications:
            return medications
        linked_names: dict[int, list[str]] = {}
        links = await MedicationInteractionEntity.filter(
            medication_id__in=[item.medication_id for item in medications],
            interaction_entity__entity_kind="DRUG",
        ).prefetch_related("interaction_entity")
        for link in links:
            linked_names.setdefault(link.medication_id, []).append(link.interaction_entity.canonical_name)

        candidates_by_id = {}
        generic_dosage_form_fallbacks_by_id: dict[int, str] = {}
        for item in medications:
            if item.medication_id in linked_names:
                continue
            full_name = normalize_interaction_name(item.name).casefold()
            strength_free_name = cls._TRAILING_STRENGTH.sub("", full_name).strip()
            generic_ingredient_name = strength_free_name
            if not cls._COMBINATION_SEPARATOR.search(strength_free_name):
                generic_ingredient_name = cls._TRAILING_GENERIC_DOSAGE_FORM.sub("", strength_free_name).strip()
                generic_dosage_form_fallbacks_by_id[item.medication_id] = (
                    generic_ingredient_name if generic_ingredient_name != strength_free_name else ""
                )
            candidates_by_id[item.medication_id] = list(
                dict.fromkeys([full_name, strength_free_name, generic_ingredient_name])
            )
        candidate_names = {name for names in candidates_by_id.values() for name in names if name}
        catalog_entities = (
            {
                entity.normalized_name: entity
                for entity in await InteractionEntity.filter(entity_kind="DRUG", normalized_name__in=candidate_names)
            }
            if candidate_names
            else {}
        )
        for medication_id, candidates in candidates_by_id.items():
            for candidate in candidates:
                if entity := catalog_entities.get(candidate):
                    if (
                        generic_dosage_form_fallbacks_by_id.get(medication_id) == candidate
                        and normalize_interaction_name(entity.canonical_name).casefold() != candidate
                    ):
                        continue
                    linked_names[medication_id] = [entity.canonical_name]
                    break
        return [
            item.model_copy(update={"interaction_names": sorted(set(linked_names.get(item.medication_id, [])))})
            for item in medications
        ]

    @staticmethod
    async def _validate_preferred_episode(
        *,
        user_id: int,
        care_episode_id: int,
    ) -> None:
        episode = await CareEpisode.filter(
            id=care_episode_id,
            user_id=user_id,
        ).first()
        if episode is None:
            raise PatientContextNotFoundError("요청한 사용자의 케어 에피소드를 찾을 수 없습니다.")
        if episode.confirmed_at is None or not episode.confirmation_hash:
            raise UnconfirmedPatientContextError("사용자가 확인하고 저장한 확정 복약정보가 아닙니다.")

    @staticmethod
    def _is_current_medication(
        medication: Medication,
        *,
        episode: CareEpisode,
        today: date,
    ) -> bool:
        start_date = episode.medication_start_date or medication.prescribed_at
        if start_date is None:
            return True
        if start_date > today:
            return False
        days = medication.days or episode.medication_days
        if days is None:
            return True
        last_day = start_date + timedelta(days=days - 1)
        return last_day >= today

    @staticmethod
    def _to_active_medication(
        medication: Medication,
    ) -> ActiveMedication:
        return ActiveMedication(
            medication_id=medication.id,
            care_episode_id=medication.care_episode_id,
            name=medication.name,
            dose=medication.dose_quantity,
            times_per_day=medication.times_per_day,
            days=medication.days,
            prescribed_at=medication.prescribed_at,
            scheduled_slots=sorted(slot.slot.value for slot in medication.slots),
        )

    # 식품영양성분 DB의 성분 컬럼과 화면 표기. 값이 있는 것만 답변에 올린다.
    # 이 자료는 오메가3를 따로 담지 않고 지방으로만 기록한다(오메가3 제품 671개 중 631개가
    # `fat_g`만 보유). 거시영양소를 빼면 오메가3 제품이 비타민 영양제처럼 보인다.
    _NUTRIENT_COLUMNS: tuple[tuple[str, str, str], ...] = (
        ("protein_g", "단백질", "g"),
        ("fat_g", "지방", "g"),
        ("carb_g", "탄수화물", "g"),
        ("sugar_g", "당류", "g"),
        ("fiber_g", "식이섬유", "g"),
        ("calcium_mg", "칼슘", "mg"),
        ("iron_mg", "철", "mg"),
        ("phosphorus_mg", "인", "mg"),
        ("potassium_mg", "칼륨", "mg"),
        ("sodium_mg", "나트륨", "mg"),
        ("vitamin_a_ug_rae", "비타민 A", "㎍RAE"),
        ("retinol_ug", "레티놀", "㎍"),
        ("beta_carotene_ug", "베타카로틴", "㎍"),
        ("thiamine_mg", "티아민", "mg"),
        ("riboflavin_mg", "리보플라빈", "mg"),
        ("niacin_mg", "니아신", "mg"),
        ("vitamin_c_mg", "비타민 C", "mg"),
        ("vitamin_d_ug", "비타민 D", "㎍"),
    )

    # 오메가3 제품은 이 자료에서 총지방으로만 기록된다. 제품명이 오메가3를 가리킬 때는
    # `지방`보다 `오메가-3`가 사용자에게 맞는 이름이다. 다만 총지방이 곧 EPA+DHA 함량은
    # 아니므로 답변에는 전체 성분을 제품 표시사항에서 확인하라는 안내를 함께 둔다.
    _OMEGA_PRODUCT_NAME = re.compile(r"오메가\s*-?\s*3|EPA|DHA", re.IGNORECASE)
    _OMEGA_FAT_LABEL = "오메가-3"

    @classmethod
    def _nutrient_amounts(cls, nutrient: object) -> list[SupplementNutrientAmount]:
        product_name = str(getattr(nutrient, "name", "") or "")
        is_omega_product = bool(cls._OMEGA_PRODUCT_NAME.search(product_name))
        amounts: list[SupplementNutrientAmount] = []
        for column, label, unit in cls._NUTRIENT_COLUMNS:
            value = getattr(nutrient, column, None)
            if value is None or Decimal(str(value)) <= 0:
                continue
            if column == "fat_g" and is_omega_product:
                label = cls._OMEGA_FAT_LABEL
            amounts.append(
                SupplementNutrientAmount(
                    name=label,
                    amount=f"{Decimal(str(value)).normalize():f}",
                    unit=unit,
                )
            )
        return amounts

    @classmethod
    def _to_active_supplement(
        cls,
        registration: UserSupplementNutrient,
    ) -> ActiveSupplement:
        return ActiveSupplement(
            registration_id=registration.id,
            supplement_nutrient_id=registration.supplement_nutrient_id,
            name=registration.supplement_nutrient.name,
            nutrients=cls._nutrient_amounts(registration.supplement_nutrient),
            dose_amount=str(registration.dose_amount),
            dose_unit=registration.dose_unit,
            start_date=registration.start_date,
            end_date=registration.end_date,
            note=registration.note,
            scheduled_slots=sorted(slot.slot.value for slot in registration.slots),
        )
