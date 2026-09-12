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
    for claim in output_value.claims:
        if claim.section_type is not KnowledgeSectionType.INTERACTION:
            continue
        for evidence_id in claim.evidence_ids:
            evidence = evidence_by_id[evidence_id]
            if KnowledgeSectionType.INTERACTION not in evidence.section_types:
                raise ValueError("상호작용 claim은 INTERACTION 근거만 참조할 수 있습니다.")
            if requested_pair_keys and not requested_pair_keys.intersection(
                evidence.pair_keys,
            ):
                raise ValueError("상호작용 claim이 요청한 상호작용 조합의 근거를 참조하지 않았습니다.")
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
