import json
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.llm.prompts.prompt_assets import (
    MedicationPromptStage,
    load_prompt_chain_stage,
)
from ai_worker.schemas.evidence_reasoning import (
    EvidenceItem,
    EvidenceReasoningInput,
    EvidenceReasoningOutput,
    InteractionEvidenceDecision,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


class InteractionEvidenceReasoningChain(Protocol):
    async def ainvoke(
        self,
        input: EvidenceReasoningInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> EvidenceReasoningOutput | dict[str, Any]: ...


class AsyncInteractionEvidenceReasoningClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> EvidenceReasoningOutput | dict[str, Any]: ...


def _validate_pair_bound_evidence(
    *,
    pair_key: str,
    evidence_ids: list[str],
    requested_pair_keys: set[str],
    evidence_by_id: dict[str, EvidenceItem],
    field_name: str,
) -> None:
    if pair_key not in requested_pair_keys:
        raise ValueError(f"{field_name} pair_key가 요청한 상호작용 조합에 없습니다.")
    for evidence_id in evidence_ids:
        evidence = evidence_by_id[evidence_id]
        if KnowledgeSectionType.INTERACTION not in evidence.section_types:
            raise ValueError(f"{field_name}은 INTERACTION 근거만 참조할 수 있습니다.")
        if pair_key not in evidence.pair_keys:
            raise ValueError(f"{field_name} pair_key가 요청한 상호작용 조합의 근거와 일치하지 않습니다.")


def _validate_claim_pair_bindings(
    *,
    output: EvidenceReasoningOutput,
    requested_pair_keys: set[str],
    evidence_by_id: dict[str, EvidenceItem],
) -> None:
    for claim in output.claims:
        if claim.section_type is not KnowledgeSectionType.INTERACTION:
            continue
        if claim.pair_key is None:
            raise ValueError("INTERACTION claim에는 pair_key가 필요합니다.")
        _validate_pair_bound_evidence(
            pair_key=claim.pair_key,
            evidence_ids=claim.evidence_ids,
            requested_pair_keys=requested_pair_keys,
            evidence_by_id=evidence_by_id,
            field_name="상호작용 claim",
        )


def _validate_action_and_conflict_pair_bindings(
    *,
    output: EvidenceReasoningOutput,
    requested_pair_keys: set[str],
    evidence_by_id: dict[str, EvidenceItem],
) -> None:
    if output.supported_action is not None:
        _validate_pair_bound_evidence(
            pair_key=output.supported_action.pair_key,
            evidence_ids=output.supported_action.evidence_ids,
            requested_pair_keys=requested_pair_keys,
            evidence_by_id=evidence_by_id,
            field_name="supported_action",
        )
    if not output.conflict_evidence_ids:
        return
    if output.conflict_pair_key is None:
        raise ValueError("충돌 근거에는 conflict_pair_key가 필요합니다.")
    _validate_pair_bound_evidence(
        pair_key=output.conflict_pair_key,
        evidence_ids=output.conflict_evidence_ids,
        requested_pair_keys=requested_pair_keys,
        evidence_by_id=evidence_by_id,
        field_name="충돌 근거",
    )


def _validate_evidence_reasoning_output(
    envelope: dict[
        str,
        EvidenceReasoningInput | EvidenceReasoningOutput | dict[str, Any],
    ],
) -> EvidenceReasoningOutput:
    input_value = EvidenceReasoningInput.model_validate(envelope["input"])
    output_value = EvidenceReasoningOutput.model_validate(envelope["output"])
    evidence_by_id = {
        item.evidence_id: item
        for item in (
            *input_value.evidence_items,
            *input_value.approved_rules,
        )
    }
    referenced_ids = {evidence_id for claim in output_value.claims for evidence_id in claim.evidence_ids}
    if output_value.supported_action is not None:
        referenced_ids.update(output_value.supported_action.evidence_ids)
    referenced_ids.update(output_value.conflict_evidence_ids)
    if unknown_ids := referenced_ids - set(evidence_by_id):
        raise ValueError(f"입력 근거 ID에 없는 값을 참조했습니다: {sorted(unknown_ids)}")

    requested_pair_keys = set(input_value.interaction_pair_keys)
    _validate_claim_pair_bindings(
        output=output_value,
        requested_pair_keys=requested_pair_keys,
        evidence_by_id=evidence_by_id,
    )
    _validate_action_and_conflict_pair_bindings(
        output=output_value,
        requested_pair_keys=requested_pair_keys,
        evidence_by_id=evidence_by_id,
    )
    if (
        KnowledgeSectionType.INTERACTION in input_value.requested_section_types
        and output_value.interaction_decision is InteractionEvidenceDecision.NOT_APPLICABLE
    ):
        raise ValueError("상호작용 요청에는 NOT_APPLICABLE 판정을 사용할 수 없습니다.")
    return output_value


def build_interaction_evidence_reasoning_chain(
    *,
    model: str,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 0,
    client: AsyncInteractionEvidenceReasoningClient | None = None,
) -> InteractionEvidenceReasoningChain:
    """상호작용 근거를 구조화해 판정하고 입력 근거 ID로 결과를 제한한다."""

    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")

    response_runnable: Runnable
    if client is not None:
        response_runnable = RunnableLambda(client.ainvoke).with_config(
            run_name="medication.evidence_reasoning.client",
        )
    else:
        response_runnable = (
            ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            .with_structured_output(
                EvidenceReasoningOutput,
                method="json_schema",
                strict=True,
            )
            .with_config(run_name="medication.evidence_reasoning.model")
        )

    prompt_document = load_prompt_chain_stage(
        MedicationPromptStage.EVIDENCE_REASONING,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompt_document.compiled_system),
            ("human", prompt_document.user),
        ]
    )

    def validate_input(
        value: EvidenceReasoningInput | dict[str, Any],
    ) -> EvidenceReasoningInput:
        if isinstance(value, EvidenceReasoningInput):
            return value
        return EvidenceReasoningInput.model_validate(value)

    def render(value: EvidenceReasoningInput):
        query_interpretation = {
            "question": value.question,
            "entity_names": value.entity_names,
            "requested_section_types": [section.value for section in value.requested_section_types],
            "interaction_pair_keys": value.interaction_pair_keys,
        }
        return prompt.format_messages(
            query_interpretation_json=json.dumps(
                query_interpretation,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            risk_profile_json=json.dumps(
                value.risk_profile,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            evidence_items_json=json.dumps(
                [item.model_dump(mode="json") for item in value.evidence_items],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            approved_rules_json=json.dumps(
                [item.model_dump(mode="json") for item in value.approved_rules],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    validated_input = RunnableLambda(validate_input).with_config(
        run_name="medication.evidence_reasoning.input",
    )
    prompted_response = (
        RunnableLambda(render).with_config(
            run_name="medication.evidence_reasoning.prompt",
        )
        | response_runnable
    )
    return (
        validated_input
        | RunnableParallel(
            input=RunnablePassthrough(),
            output=prompted_response,
        )
        | RunnableLambda(_validate_evidence_reasoning_output).with_config(
            run_name="medication.evidence_reasoning.output",
        )
    ).with_types(
        input_type=EvidenceReasoningInput,
        output_type=EvidenceReasoningOutput,
    )
