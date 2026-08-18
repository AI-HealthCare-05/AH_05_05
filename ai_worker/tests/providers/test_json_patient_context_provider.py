from pathlib import Path

import pytest

from ai_worker.providers.json_patient_context_provider import (
    JsonPatientContextProvider,
)


@pytest.fixture
def provider() -> JsonPatientContextProvider:
    sample_path = Path(__file__).resolve().parents[1] / "fixtures" / "patient_sample.json"
    return JsonPatientContextProvider(sample_path)


@pytest.mark.asyncio
async def test_get_patient_context_success(
    provider: JsonPatientContextProvider,
) -> None:
    result = await provider.get_patient_context(
        user_id=1,
        care_episode_id=100,
    )

    assert result.user_id == 1
    assert result.care_episode_id == 100
    assert result.medications[0].drug_name == "테스트정"


@pytest.mark.asyncio
async def test_get_patient_context_with_wrong_user_id(
    provider: JsonPatientContextProvider,
) -> None:
    with pytest.raises(ValueError, match="사용자"):
        await provider.get_patient_context(
            user_id=999,
            care_episode_id=100,
        )


@pytest.mark.asyncio
async def test_get_patient_context_with_wrong_care_episode_id(
    provider: JsonPatientContextProvider,
) -> None:
    with pytest.raises(ValueError, match="케어 ID"):
        await provider.get_patient_context(
            user_id=1,
            care_episode_id=999,
        )
