import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.medication_ocr_v3.domain.grounding import EvidenceBlock, EvidenceCatalog
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.calls = 0
        self.output_text = json.dumps({"dispensedDateBlockIds": [], "medications": []})

    async def create(self, **kwargs: object) -> object:
        self.calls += 1
        self.kwargs = kwargs
        return SimpleNamespace(
            status="completed",
            output=[],
            output_text=self.output_text,
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_grounded_structurer_uses_deterministic_temperature() -> None:
    client = _FakeClient()
    structurer = OpenAIGroundedStructurer(api_key="test-key", client=client)
    catalog = EvidenceCatalog(blocks=(), date_candidates=(), rows=())

    await structurer.select(catalog)

    assert client.responses.kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_semantic_provider_sends_full_field_schema_and_retains_privacy_request_options() -> None:
    from app.services.medication_ocr_v3.domain.grounding import SemanticGroundingSelection

    client = _FakeClient()
    provider = OpenAIGroundedStructurer(api_key="test-key", client=client, review_mode="semantic")
    selection = await provider.select(EvidenceCatalog(blocks=(), date_candidates=(), rows=()))

    assert isinstance(selection, SemanticGroundingSelection)
    request = client.responses.kwargs
    assert json.loads(request["input"])["schemaVersion"] == "semantic-v1"
    schema = request["text"]["format"]["schema"]
    fields = schema["$defs"]["SemanticMedicationSelection"]["required"]
    assert set(fields) == {"rowId", "name", "strength", "doseQuantity", "timesPerDay", "days"}
    assert request["store"] is False
    assert request["truncation"] == "disabled"


@pytest.mark.asyncio
async def test_legacy_prompt_versions_are_pinnable_without_changing_request_cost_contract():
    prompts = Path(__file__).resolve().parents[2] / "app/services/medication_ocr_v3/prompts"
    requests = []
    for version in ("medication_grounding_v3", "medication_grounding_v4"):
        client = _FakeClient()
        provider = OpenAIGroundedStructurer(api_key="test-key", client=client, legacy_prompt_version=version)
        await provider.select(EvidenceCatalog(blocks=(), date_candidates=(), rows=()))
        assert provider.prompt_version == version
        assert client.responses.kwargs["instructions"] == (prompts / f"{version}.md").read_text(encoding="utf-8")
        assert client.responses.calls == 1
        requests.append(client.responses.kwargs)
    # Keep the compact prompt independent of the response wait budget.
    assert len(requests[1]["instructions"]) <= 3200
    assert {k: v for k, v in requests[0].items() if k != "instructions"} == {
        k: v for k, v in requests[1].items() if k != "instructions"
    }
    assert OpenAIGroundedStructurer(api_key="test-key").prompt_version == "medication_grounding_v4"


@pytest.mark.parametrize("version", ["../other", "medication_grounding_v99"])
def test_unknown_legacy_prompt_versions_are_rejected_before_any_request(version):
    with pytest.raises(ValueError, match="prompt version"):
        OpenAIGroundedStructurer(api_key="test-key", legacy_prompt_version=version)


@pytest.mark.asyncio
async def test_legacy_response_can_finish_after_the_previous_short_deadline():
    client = _FakeClient()
    original_create = client.responses.create

    async def delayed_response(**kwargs):
        await asyncio.sleep(2.6)
        return await original_create(**kwargs)

    client.responses.create = delayed_response
    provider = OpenAIGroundedStructurer(api_key="test-key", client=client)
    result = await provider.select(EvidenceCatalog(blocks=(), date_candidates=(), rows=()))
    assert result.medications == []
    assert client.responses.calls == 1


@pytest.mark.asyncio
async def test_legacy_response_wait_is_bounded_and_does_not_retry(monkeypatch):
    from app.services.medication_ocr_v3.providers import openai_grounded as module

    monkeypatch.setattr(module, "LEGACY_RESPONSE_TIMEOUT_SECONDS", 0.01, raising=False)
    client = _FakeClient()
    calls = 0

    async def slow_response(**kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return SimpleNamespace(
            status="completed", output=[], output_text='{"dispensedDateBlockIds":[],"medications":[]}'
        )

    client.responses.create = slow_response
    provider = OpenAIGroundedStructurer(api_key="test-key", client=client)
    with pytest.raises(module.LlmProviderError) as caught:
        await provider.select(EvidenceCatalog(blocks=(), date_candidates=(), rows=()))
    assert caught.value.code is module.LlmErrorCode.LLM_TIMEOUT
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version,text,expected",
    [
        ("medication_grounding_v3", "2025.10.25", ["date-a"]),
        ("medication_grounding_v4", "2025.10.25", []),
        ("medication_grounding_v4", "조제일 2025.10.25", ["date-a"]),
        ("medication_grounding_v4", "dispensed date 2025.10.25", ["date-a"]),
    ],
)
async def test_v4_rejects_unlabeled_date_choice_without_rewriting_legacy(version, text, expected):
    client = _FakeClient()
    client.responses.output_text = json.dumps({"dispensedDateBlockIds": ["date-a"], "medications": []})
    other_text = "조제일 2025.10.30" if text == "2025.10.25" else "사용기한 2025.10.30"
    dates = tuple(
        EvidenceBlock(key, value, 0.99, AxisAlignedBBox(0, 0, 100, 20), key, (), ("dispensedDate",))
        for key, value in (("date-a", text), ("date-b", other_text))
    )
    provider = OpenAIGroundedStructurer(api_key="test-key", client=client, legacy_prompt_version=version)
    result = await provider.select(EvidenceCatalog(blocks=dates, date_candidates=dates, rows=()))
    assert result.dispensed_date_block_ids == expected
    assert client.responses.calls == 1
