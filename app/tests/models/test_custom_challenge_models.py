from datetime import date, datetime, timedelta
from importlib import import_module

import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError
from tortoise.fields.relational import OnDelete

from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.enums import ChallengeParticipationStatus, MealSlot
from app.models.users import User


def _custom_models():
    module = import_module("app.models.custom_challenges")
    return (
        module.CustomChallengeType,
        module.CustomChallengeParticipation,
        module.CustomChallengeTarget,
        module.CustomChallengeOccurrence,
    )


async def _create_user(*, email: str = "custom-challenge@example.com") -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name="맞춤 챌린지 테스트",
    )


async def _create_template() -> CustomChallengeTemplate:
    group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CHK_TYPE2_TEST",
        group_name="맞춤 인증 방식",
    )
    check_type = await CommonCode.create(
        group=group,
        detail_code="MEDICATION",
        detail_name="복약 인증",
    )
    return await CustomChallengeTemplate.create(
        name="약 잘 챙겨 먹기",
        check_type=check_type,
    )


async def _create_participation(*, idempotency_key: str = "request-1"):
    challenge_type, participation_model, _, _ = _custom_models()
    user = await _create_user()
    template = await _create_template()
    participation = await participation_model.create(
        user=user,
        template=template,
        challenge_type=challenge_type.MEDICATION,
        challenge_name=template.name,
        idempotency_key=idempotency_key,
        end_at=datetime.now() + timedelta(days=7),
    )
    return user, template, participation


async def _create_target_and_occurrence():
    _, _, target_model, occurrence_model = _custom_models()
    user, template, participation = await _create_participation()
    care_episode = await CareEpisode.create(user=user)
    target = await target_model.create(
        participation=participation,
        care_episode=care_episode,
        source_id_snapshot=care_episode.id,
        target_name_snapshot="감기 처방",
    )
    occurrence = await occurrence_model.create(
        target=target,
        scheduled_date=date(2026, 9, 9),
        slot=MealSlot.MORNING,
        scheduled_at=datetime(2026, 9, 9, 8),
    )
    return user, template, participation, care_episode, target, occurrence


class TestCustomChallengeModels(TestCase):
    def test_exact_minimal_model_fields(self) -> None:
        _, participation, target, occurrence = _custom_models()

        assert set(participation._meta.fields_db_projection.values()) == {
            "id",
            "user_id",
            "template_id",
            "challenge_type",
            "challenge_name",
            "idempotency_key",
            "joined_at",
            "end_at",
            "status",
        }
        assert set(target._meta.fields_db_projection.values()) == {
            "id",
            "participation_id",
            "care_episode_id",
            "supplement_registration_id",
            "follow_up_visit_id",
            "source_id_snapshot",
            "target_name_snapshot",
        }
        assert set(occurrence._meta.fields_db_projection.values()) == {
            "id",
            "target_id",
            "scheduled_date",
            "slot",
            "scheduled_at",
        }

    def test_enums_unique_constraints_and_delete_policies_match_storage_contract(self) -> None:
        challenge_type, participation, target, occurrence = _custom_models()

        assert {item.value for item in challenge_type} == {"MEDICATION", "SUPPLEMENT", "VISIT"}
        assert participation._meta.fields_map["status"].enum_type is ChallengeParticipationStatus
        assert occurrence._meta.fields_map["slot"].enum_type is MealSlot
        assert participation._meta.unique_together == (("user", "idempotency_key"),)
        assert target._meta.unique_together == (("participation", "source_id_snapshot"),)
        assert occurrence._meta.unique_together == (("target", "scheduled_date", "slot"),)

        participation_fields = participation._meta.fields_map
        target_fields = target._meta.fields_map
        occurrence_fields = occurrence._meta.fields_map
        assert participation_fields["user"].on_delete is OnDelete.CASCADE
        assert participation_fields["template"].on_delete is OnDelete.RESTRICT
        assert target_fields["participation"].on_delete is OnDelete.CASCADE
        assert target_fields["care_episode"].on_delete is OnDelete.SET_NULL
        assert target_fields["supplement_registration"].on_delete is OnDelete.SET_NULL
        assert target_fields["follow_up_visit"].on_delete is OnDelete.SET_NULL
        assert target_fields["care_episode"].null is True
        assert target_fields["supplement_registration"].null is True
        assert target_fields["follow_up_visit"].null is True
        assert occurrence_fields["target"].on_delete is OnDelete.CASCADE

    async def test_rejects_duplicate_participation_request_for_user(self) -> None:
        challenge_type, participation_model, _, _ = _custom_models()
        user, template, _ = await _create_participation()

        with pytest.raises(IntegrityError):
            await participation_model.create(
                user=user,
                template=template,
                challenge_type=challenge_type.MEDICATION,
                challenge_name=template.name,
                idempotency_key="request-1",
                end_at=datetime.now() + timedelta(days=7),
            )

    async def test_rejects_duplicate_target_source_for_participation(self) -> None:
        _, _, target_model, _ = _custom_models()
        user, _, participation = await _create_participation()
        care_episode = await CareEpisode.create(user=user)
        values = {
            "participation": participation,
            "care_episode": care_episode,
            "source_id_snapshot": care_episode.id,
            "target_name_snapshot": "감기 처방",
        }
        await target_model.create(**values)

        with pytest.raises(IntegrityError):
            await target_model.create(**values)

    async def test_rejects_duplicate_occurrence_slot_for_target(self) -> None:
        _, _, _, occurrence_model = _custom_models()
        *_, target, occurrence = await _create_target_and_occurrence()

        with pytest.raises(IntegrityError):
            await occurrence_model.create(
                target=target,
                scheduled_date=occurrence.scheduled_date,
                slot=occurrence.slot,
                scheduled_at=datetime(2026, 9, 9, 9),
            )

    async def test_source_deletion_nullifies_fk_without_deleting_history(self) -> None:
        _, _, target_model, occurrence_model = _custom_models()
        *_, care_episode, target, occurrence = await _create_target_and_occurrence()

        await care_episode.delete()

        stored_target = await target_model.get(id=target.id)
        assert stored_target.care_episode_id is None
        assert stored_target.source_id_snapshot == care_episode.id
        assert stored_target.target_name_snapshot == "감기 처방"
        assert await occurrence_model.filter(id=occurrence.id, target_id=target.id).exists()

    async def test_participation_deletion_cascades_to_targets_and_occurrences(self) -> None:
        _, _, target_model, occurrence_model = _custom_models()
        *_, participation, _, target, occurrence = await _create_target_and_occurrence()

        await participation.delete()

        assert not await target_model.filter(id=target.id).exists()
        assert not await occurrence_model.filter(id=occurrence.id).exists()

    async def test_target_deletion_cascades_to_occurrences(self) -> None:
        _, _, _, occurrence_model = _custom_models()
        *_, target, occurrence = await _create_target_and_occurrence()

        await target.delete()

        assert not await occurrence_model.filter(id=occurrence.id).exists()

    async def test_template_deletion_is_restricted_while_participation_exists(self) -> None:
        _, participation_model, _, _ = _custom_models()
        _, template, participation = await _create_participation()

        with pytest.raises(IntegrityError):
            await template.delete()

        assert await CustomChallengeTemplate.filter(id=template.id).exists()
        assert await participation_model.filter(id=participation.id).exists()
