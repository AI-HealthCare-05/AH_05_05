from tortoise.fields.relational import OnDelete

import app.models as models
import app.models.enums as enums
from app.core.db.databases import TORTOISE_APP_MODELS


def test_challenge_domain_models_are_registered() -> None:
    expected_models = {
        "Badge",
        "Challenge",
        "CustomChallengeTemplate",
        "UserChallenge",
        "ChallengeProgress",
        "ChallengeVerification",
        "UserBadge",
    }

    assert expected_models.issubset(set(dir(models)))
    assert "app.models.challenges" in TORTOISE_APP_MODELS


def test_challenge_domain_models_expose_tables_and_unique_constraints() -> None:
    assert models.Badge._meta.db_table == "badges"
    assert models.Challenge._meta.db_table == "challenges"
    assert models.CustomChallengeTemplate._meta.db_table == "custom_challenge_templates"
    assert models.UserChallenge._meta.db_table == "user_challenges"
    assert models.ChallengeProgress._meta.db_table == "challenge_progress"
    assert models.ChallengeVerification._meta.db_table == "challenge_verifications"
    assert models.UserBadge._meta.db_table == "user_badges"

    assert models.ChallengeProgress._meta.unique_together == (("user_challenge", "period_start", "period_end"),)
    assert models.UserBadge._meta.unique_together == (("user_challenge", "badge"),)


def test_challenge_domain_models_use_fixed_status_enums() -> None:
    assert hasattr(enums, "ChallengeParticipationStatus")
    assert hasattr(enums, "ChallengeVerificationStatus")
    assert hasattr(enums, "BadgeAwardStatus")
    assert models.UserChallenge._meta.fields_map["status"].enum_type is enums.ChallengeParticipationStatus
    assert models.ChallengeVerification._meta.fields_map["status"].enum_type is enums.ChallengeVerificationStatus
    assert models.UserBadge._meta.fields_map["status"].enum_type is enums.BadgeAwardStatus


def test_expired_participation_status_can_be_loaded_from_storage() -> None:
    participation = models.UserChallenge(status="EXPIRED")

    assert participation.status.value == "EXPIRED"


def test_generated_challenge_schema_enforces_one_verification_per_day() -> None:
    assert models.ChallengeVerification._meta.unique_together == (("user_challenge", "verification_date"),)


def test_challenge_common_code_and_history_relationships_are_restrictive() -> None:
    challenge_fields = models.Challenge._meta.fields_map
    verification_fields = models.ChallengeVerification._meta.fields_map

    assert challenge_fields["challenge_type"].model_name == "models.CommonCode"
    assert challenge_fields["challenge_period"].model_name == "models.CommonCode"
    assert challenge_fields["check_type"].model_name == "models.CommonCode"
    assert challenge_fields["check_frequency"].model_name == "models.CommonCode"
    assert challenge_fields["reward_badge"].model_name == "models.Badge"
    assert verification_fields["reviewed_by_admin"].null is True


def test_custom_challenge_template_exposes_management_fields() -> None:
    badge_fields = models.Badge._meta.fields_map
    fields = models.CustomChallengeTemplate._meta.fields_map

    assert badge_fields["type"].model_name == "models.CommonCode"
    assert badge_fields["type"].null is True
    assert badge_fields["type_id"].source_field == "type"
    assert fields["name"].max_length == 100
    assert fields["name"].unique is True
    assert fields["is_active"].default is True
    assert fields["check_type"].model_name == "models.CommonCode"
    assert fields["check_type"].on_delete is OnDelete.RESTRICT
    assert fields["challenge_type"].model_name == "models.CommonCode"
    assert fields["challenge_type"].null is True
    assert fields["challenge_type_id"].source_field == "challenge_type"
    assert fields["reward_badge"].model_name == "models.Badge"
    assert fields["reward_badge"].null is True
    assert fields["created_by_admin"].null is True
    assert fields["updated_by_admin"].null is True
