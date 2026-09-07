from importlib import import_module

from aerich.utils import decompress_dict


def test_ocr_migrations_extend_email_verification_without_dropping_its_state() -> None:
    prefix = "app.core.db.migrations.models."
    email = import_module(prefix + "31_20260907131651_add_email_verifications")
    hospital = import_module(prefix + "32_20260907223000_add_care_episode_hospital_name")
    envelope = import_module(prefix + "33_20260907223001_stage_results_envelope")
    previous = decompress_dict(email.MODELS_STATE)
    combined = decompress_dict(hospital.MODELS_STATE)
    final = decompress_dict(envelope.MODELS_STATE)
    assert set(combined) == set(previous)
    assert combined["models.EmailVerification"] == previous["models.EmailVerification"]
    assert final == combined
    fields = {field["name"]: field for field in final["models.CareEpisode"]["data_fields"]}
    assert fields["hospital_name"]["nullable"] is True
    assert fields["hospital_name"]["constraints"]["max_length"] == 255
