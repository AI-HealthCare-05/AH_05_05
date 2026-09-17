"""Server-owned evidence cards with position-only Korean whitespace selection."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, Protocol, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ConfigDict, Field, SecretStr, ValidationError, create_model

from ai_worker.domain.errors import IntakeReportGenerationError
from ai_worker.llm.prompts.prompt_assets import load_prompt_asset
from ai_worker.reports.v11_cards import (
    V11EvidenceCatalog,
    build_canonical_card_plan,
    build_evidence_catalog,
    render_cards,
    render_cards_markdown,
    validate_card_plan,
)
from ai_worker.reports.v11_spacing_repair import (
    SpacingProposalMutationError,
    SpacingRepairRequest,
    SpacingRepairResponse,
    payload_spacing_pattern,
    prepare_spacing_repair,
    project_spacing_proposals,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCards, IntakeReportCardsPlan


async def _gather_cancel_on_failure[T](coroutines: list[Coroutine[Any, Any, T]]) -> list[T]:
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


if TYPE_CHECKING:
    from ai_worker.schemas.intake_report import IntakeReportDraft, IntakeReportGenerationOutcome


logger = logging.getLogger(__name__)


class AsyncSpacingRepairClient(Protocol):
    async def ainvoke(self, messages: Any) -> SpacingRepairResponse | dict[str, Any]: ...


class _SchemaBoundSpacingClient:
    """Validate whitespace proposals, then return server-computed positions only."""

    def __init__(self, model: Any) -> None:
        self._model = model

    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
        fields = json.loads(messages[1].content)["fields"]
        originals = {
            f"f{index}": "".join(chunk["text"] for chunk in field["chunks"]) for index, field in enumerate(fields)
        }
        field_definitions: dict[str, Any] = {
            key: (str, Field(pattern=payload_spacing_pattern(fields[index]["chunks"])))
            for index, key in enumerate(originals)
        }
        schema = create_model(
            "WhitespaceProposals",
            __config__=ConfigDict(extra="forbid"),
            **field_definitions,
        )
        # Retry examples use the same transport schema, never the internal mapping.
        model_messages = list(messages)
        model_messages[1] = HumanMessage(content=json.dumps(originals, ensure_ascii=False))
        for index, message in enumerate(model_messages[2:], 2):
            if isinstance(message, AIMessage):
                if not isinstance(message.content, str):
                    raise ValueError("spacing retry content must be a JSON string")
                repairs = {repair["key"]: repair for repair in json.loads(message.content)["repairs"]}
                flattened = {}
                for field_index, field in enumerate(fields):
                    chunks = {chunk["index"]: chunk for chunk in repairs[field["key"]]["chunks"]}
                    flattened[f"f{field_index}"] = "".join(
                        character + (" " if offset in chunks[chunk["index"]]["spaceAfter"] else "")
                        for chunk in field["chunks"]
                        for offset, character in enumerate(chunk["text"], 1)
                    )
                model_messages[index] = AIMessage(content=json.dumps(flattened, ensure_ascii=False))
        response = (
            await self._model.with_structured_output(
                schema,
                method="json_schema",
                strict=True,
            )
            .with_config(run_name="intake_report_cards.spacing_model")
            .ainvoke(model_messages)
        )
        return project_spacing_proposals(fields, schema.model_validate(response).model_dump())


class AsyncPlainLanguageRefiner(Protocol):
    async def refine(self, cards: IntakeReportCards) -> IntakeReportCards: ...


def _spacing_messages(
    request: SpacingRepairRequest,
    repair_error: str,
    previous_response: Any = None,
    batch: tuple[tuple[int, int], ...] | None = None,
) -> list[Any]:
    messages = [
        SystemMessage(content=load_prompt_asset("intake_report_spacing.md")),
        HumanMessage(content=json.dumps({"fields": request.payload(batch)}, ensure_ascii=False, separators=(",", ":"))),
    ]
    if repair_error:
        if previous_response is not None:
            serialized = (
                previous_response.model_dump(mode="json", by_alias=True)
                if isinstance(previous_response, SpacingRepairResponse)
                else previous_response
            )
            messages.append(AIMessage(content=json.dumps(serialized, ensure_ascii=False)))
        messages.append(
            HumanMessage(content=load_prompt_asset("intake_report_spacing_retry.md").format(repair_error=repair_error))
        )
    return messages


class OpenAIIntakeReportCardsGenerator:
    """Build the complete plan on the server; the model only selects spaces."""

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | None = None,
        spacing_client: AsyncSpacingRepairClient | None = None,
        plain_language_refiner: AsyncPlainLanguageRefiner | None = None,
        enable_plain_language: bool = False,
        timeout_seconds: float = 75.0,
        max_retries: int = 2,
        max_repair_attempts: int = 2,
        generation_timeout_seconds: float = 90.0,
        include_fixed_lifestyle_guidance: bool = True,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        if not 0 <= max_repair_attempts <= 2:
            raise ValueError("수정 재생성은 0~2회만 허용합니다.")
        if timeout_seconds <= 0:
            raise ValueError("모델 요청 제한 시간은 양수여야 합니다.")
        if generation_timeout_seconds <= 0:
            raise ValueError("보고서 생성 제한 시간은 양수여야 합니다.")
        self._model_name = normalized_model
        self._request_timeout_seconds = timeout_seconds
        self._max_repair_attempts = max_repair_attempts
        self._generation_timeout_seconds = generation_timeout_seconds
        self._include_fixed_lifestyle_guidance = include_fixed_lifestyle_guidance
        # Evidence-only is the default: model-reviewed paraphrases are not
        # equivalent to the deterministic source-character validation below.
        self._plain_language_refiner = plain_language_refiner if enable_plain_language else None
        if spacing_client is not None:
            self._spacing_client = spacing_client
        else:
            model_client = ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            self._spacing_client = _SchemaBoundSpacingClient(model_client)
        if enable_plain_language and self._plain_language_refiner is None:
            from ai_worker.reports.v11_plain_language import (
                AsyncPlainLanguageClient,
                PlainLanguageEdits,
                PlainLanguageRefiner,
                PlainLanguageReview,
            )

            # Experimental opt-in only; the production service disables rewriting.
            # Refinement is still charged to the same report deadline.
            display_client = ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=25.0,
                max_retries=0,
            )
            self._plain_language_refiner = PlainLanguageRefiner(
                # Both clients are invoked positionally; Runnable names that argument `input`.
                writer=cast(
                    AsyncPlainLanguageClient,
                    display_client.with_structured_output(
                        PlainLanguageEdits,
                        method="json_schema",
                        strict=True,
                    ).with_config(run_name="intake_report_cards.plain_language"),
                ),
                reviewer=cast(
                    AsyncPlainLanguageClient,
                    display_client.with_structured_output(
                        PlainLanguageReview,
                        method="json_schema",
                        strict=True,
                    ).with_config(run_name="intake_report_cards.plain_language_review"),
                ),
                timeout_seconds=25.0,
            )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def request_timeout_seconds(self) -> float:
        return self._request_timeout_seconds

    @property
    def generation_timeout_seconds(self) -> float:
        return self._generation_timeout_seconds

    @property
    def uses_knowledge_evidence(self) -> bool:
        return False

    async def generate(self, *, draft: IntakeReportDraft) -> IntakeReportGenerationOutcome:
        from ai_worker.schemas.intake_report import IntakeReportGenerationOutcome

        deadline = asyncio.get_running_loop().time() + self._generation_timeout_seconds
        catalog = build_evidence_catalog(
            draft,
            include_fixed_lifestyle_guidance=self._include_fixed_lifestyle_guidance,
        )
        try:
            async with asyncio.timeout_at(deadline):
                plan = await self._generate_batched_plan(catalog)
        except TimeoutError as error:
            raise IntakeReportGenerationError(reason_code="TIMEOUT") from error
        cards = render_cards(plan, catalog, draft)
        if self._plain_language_refiner is not None:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining > 0:
                try:
                    async with asyncio.timeout(remaining):
                        cards = await self._plain_language_refiner.refine(cards)
                except TimeoutError:
                    pass  # Keep the canonical cards; never extend the report deadline.
        return IntakeReportGenerationOutcome(
            report_markdown=render_cards_markdown(cards, draft),
            cards=cards,
            fallback_used=False,
        )

    async def _generate_batched_plan(self, catalog: V11EvidenceCatalog) -> IntakeReportCardsPlan:
        semaphore = asyncio.Semaphore(3)
        subcatalogs = [
            V11EvidenceCatalog(
                medications={item_id: medication},
                interactions=(),
                lifestyle=(),
                sources=tuple(
                    source
                    for source in catalog.sources
                    if source.id in {source_id for fact in medication.facts for source_id in fact.source_ids}
                ),
            )
            for item_id, medication in catalog.medications.items()
        ]
        if catalog.interactions or catalog.lifestyle:
            subcatalogs.append(
                V11EvidenceCatalog(
                    medications={},
                    interactions=catalog.interactions,
                    lifestyle=catalog.lifestyle,
                    sources=catalog.sources,
                )
            )
        if not subcatalogs:
            return validate_card_plan(IntakeReportCardsPlan(), catalog)

        async def generate_one(subcatalog: V11EvidenceCatalog) -> IntakeReportCardsPlan:
            return await self._generate_valid_plan(subcatalog, request_semaphore=semaphore)

        partial_plans = await _gather_cancel_on_failure([generate_one(subcatalog) for subcatalog in subcatalogs])

        medication_selections = [selection for partial_plan in partial_plans for selection in partial_plan.medications]
        composition_plan = partial_plans[-1] if (catalog.interactions or catalog.lifestyle) else None
        combined = IntakeReportCardsPlan(
            medications=medication_selections,
            interactions=composition_plan.interactions if composition_plan is not None else [],
            lifestyle=composition_plan.lifestyle if composition_plan is not None else [],
        )
        return validate_card_plan(combined, catalog)

    async def _generate_valid_plan(  # noqa: C901 - repair retries preserve per-batch source coverage
        self, catalog: V11EvidenceCatalog, *, request_semaphore: asyncio.Semaphore | None = None
    ) -> IntakeReportCardsPlan:
        plan = build_canonical_card_plan(catalog)
        # Dense-run validation alone misses short warnings and numeric dosing prose.
        request = prepare_spacing_repair(plan, catalog, review_all_text=True)
        if request is None:
            try:
                return validate_card_plan(plan, catalog)
            except ValueError as error:
                # Unsupported source lengths never bypass the final text guards.
                raise IntakeReportGenerationError(
                    reason_code="VALIDATION_FAILED",
                    issue_codes=("TEXT_SPACING_REQUIRED",),
                ) from error
        semaphore = request_semaphore if request_semaphore is not None else asyncio.Semaphore(3)

        async def repair_batch(
            batch: tuple[tuple[int, int], ...],
            repair_error: str = "",
            previous_response: Any = None,
        ) -> tuple[tuple[tuple[int, int], ...], Any]:
            spacing_error = repair_error
            for attempt in range(self._max_repair_attempts + 1):
                response: Any = None
                try:
                    try:
                        async with semaphore:
                            response = await self._spacing_client.ainvoke(
                                _spacing_messages(request, spacing_error, previous_response, batch)
                            )
                    except (SpacingProposalMutationError, ValidationError):
                        raise
                    except Exception as error:
                        raise IntakeReportGenerationError(reason_code="CLIENT_ERROR") from error
                    request.validate_batch_response(batch, response)
                    return batch, response
                except (ValueError, ValidationError) as error:
                    code = str(error).split(":", 1)[0]
                    if code not in {
                        "SPACING_REPAIR_CHUNKS",
                        "SPACING_REPAIR_COVERAGE",
                        "SPACING_REPAIR_INVALID",
                        "SPACING_REPAIR_EXCESSIVE",
                        "SPACING_PROPOSAL_MUTATION",
                    }:
                        code = "SPACING_REPAIR_SCHEMA"
                    previous_response = response
                    spacing_error = code
                    logger.warning(
                        "intake_report_cards.validation_failed model=%s attempt=%d issue=%s",
                        self._model_name,
                        attempt,
                        code,
                    )
            raise IntakeReportGenerationError(reason_code="VALIDATION_FAILED", issue_codes=(spacing_error,))

        batches = request.batches()
        responses_by_batch = dict(await _gather_cancel_on_failure([repair_batch(batch) for batch in batches]))
        for repair_round in range(self._max_repair_attempts + 1):
            batch_responses = [(batch, responses_by_batch[batch]) for batch in batches]
            try:
                return validate_card_plan(request.apply_batches(batch_responses), catalog)
            except (ValueError, ValidationError) as error:
                code = str(error).split(":", 1)[0]
                if code not in {"SPACING_REPAIR_EXCESSIVE", "SPACING_REPAIR_INVALID"}:
                    code = "SPACING_REPAIR_SCHEMA"
                if repair_round >= self._max_repair_attempts:
                    raise IntakeReportGenerationError(reason_code="VALIDATION_FAILED", issue_codes=(code,)) from error
                invalid_fields = request.invalid_field_indexes(batch_responses)
                retry_batches = [
                    batch for batch in batches if any(field_index in invalid_fields for field_index, _ in batch)
                ]
                if not retry_batches:
                    raise IntakeReportGenerationError(reason_code="VALIDATION_FAILED", issue_codes=(code,)) from error
                retries = await _gather_cancel_on_failure(
                    [repair_batch(batch, code, responses_by_batch[batch]) for batch in retry_batches]
                )
                responses_by_batch.update(retries)
        raise AssertionError("spacing repair retry loop did not return or raise")


def build_intake_report_cards_generator(
    *,
    model: str,
    api_key: SecretStr | None = None,
    spacing_client: AsyncSpacingRepairClient | None = None,
    timeout_seconds: float = 75.0,
    max_retries: int = 2,
    generation_timeout_seconds: float = 90.0,
) -> OpenAIIntakeReportCardsGenerator:
    return OpenAIIntakeReportCardsGenerator(
        model=model,
        api_key=api_key,
        spacing_client=spacing_client,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        generation_timeout_seconds=generation_timeout_seconds,
    )
