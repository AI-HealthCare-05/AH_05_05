# Intake Report API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인증 사용자의 활성 복용약·영양제를 한 번에 분석해 카드·표·차트 데이터와 안전한 Markdown 보고서를 반환하는 `POST /api/v1/intake-reports`를 만든다.

**Architecture:** 채팅 세션과 질문 처리 경로를 재사용하지 않고, `GenerateIntakeReportUseCase`가 활성 복용정보·제품 가이드·승인 상호작용 규칙·제한된 Qdrant 근거를 모아 결정론적 초안을 만든다. 전용 LCEL 체인과 구조화 LLM 출력은 이 초안의 한국어 Markdown 표현만 정리하며, 검증 실패 시 결정론적 Markdown으로 대체한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Tortoise ORM, MySQL, Qdrant, LangChain 1.x LCEL, langchain-openai, OpenAI structured output, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-08-intake-report-api-design.md`

## Global Constraints

- Endpoint는 `POST /api/v1/intake-reports`이고 Bearer 인증이 필수다.
- Body는 `{}`이며 `focus`, 제품 ID, 세션 ID를 받지 않는다.
- 현재 활성 의약품과 영양제를 항상 함께 분석한다.
- 보고서 이력 테이블·마이그레이션·채팅 세션·채팅 메시지를 만들거나 변경하지 않는다.
- RDBMS·승인 규칙·Qdrant 근거 안에서만 설명하며, 근거 부재를 안전하다는 뜻으로 바꾸지 않는다.
- 복용 시작·중단·증량·감량·복용 간격 변경·진단·처방을 출력하지 않는다.
- `EMPTY`, `PARTIAL`, `COMPLETED`는 모두 200 응답이며, 핵심 복용정보 조회가 불가할 때만 503을 반환한다.
- Markdown은 `docs/intake-report-output-template.md`의 허용 요소만 사용한다.
- 기존 Chat Router, ChatApplicationService, 채팅 세션, SSE의 동작을 바꾸지 않는다.
- 모든 구현은 RED → GREEN → REFACTOR 순서를 따른다.
- 커밋 메시지는 `[feature/311][임경수]` 접두사를 사용한다.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `ai_worker/schemas/intake_report.py` | 보고서 입력·초안·카드·표·차트·LLM 결과의 불변 계약 |
| `ai_worker/assemblers/intake_report_assembler.py` | 활성 복용정보와 근거를 결정론적 카드·표·fallback Markdown으로 변환 |
| `ai_worker/use_cases/generate_intake_report.py` | RDBMS·규칙·Qdrant 조회 순서와 부분 실패 정책 |
| `ai_worker/services/intake_report_core_service.py` | 보고서 UseCase 조립과 AI Worker 진입점 |
| `ai_worker/chains/intake_report_chain.py` | 구조화 입력 → Prompt → 구조화 LLM 출력 LCEL 체인 |
| `ai_worker/llm/generators/intake_report_generator.py` | OpenAI 구조화 출력과 fallback 처리 |
| `ai_worker/llm/prompts/assets/intake_report_prompt_v1.md` | 6요소 보고서 프롬프트와 JSON 출력 계약 |
| `ai_worker/safety/intake_report_validator.py` | 금지 복용 지시·근거 없는 안전 결론·허용 Markdown 검사 |
| `app/services/intake_report.py` | API 타임아웃·LangSmith trace·Core 호출·View 변환 |
| `app/dependencies/intake_report.py` | FastAPI 앱 단위 Report Core/Qdrant 재사용 |
| `app/dtos/intake_reports.py` | camelCase HTTP 응답 DTO |
| `app/apis/v1/intake_report_router.py` | Router·ReDoc 계약·인증·오류 응답 |

## Task 1: 활성 복용정보와 보고서 스키마 계약

**Files:**
- Modify: `ai_worker/schemas/medication_chat.py`
- Modify: `ai_worker/providers/db_active_intake_context_provider.py`
- Create: `ai_worker/schemas/intake_report.py`
- Test: `ai_worker/tests/providers/test_db_active_intake_context_provider.py`
- Create: `ai_worker/tests/schemas/test_intake_report_schema.py`

**Interfaces:**
- Produces: `ActiveMedication.scheduled_slots: list[str]`, `ActiveSupplement.scheduled_slots: list[str]`
- Produces: `IntakeReportStatus`, `IntakeReportDraft`, `IntakeReportResult`, `IntakeReportReviewCard`, `IntakeReportCurrentStackItem`

- [ ] **Step 1: 활성 복용 시간과 빈 보고서 스키마의 실패 테스트를 작성한다.**

```python
async def test_provider_includes_medication_and_supplement_slots() -> None:
    context = await DbActiveIntakeContextProvider().get_active_context(
        user_id=user.id,
        care_episode_id=None,
    )

    assert context.medications[0].scheduled_slots == ["MORNING"]
    assert context.supplements[0].scheduled_slots == ["BEDTIME"]


def test_empty_report_requires_empty_cards_and_markdown() -> None:
    report = IntakeReportResult.empty(user_id=1)

    assert report.status == IntakeReportStatus.EMPTY
    assert report.current_stack == []
    assert report.review_cards == []
    assert "현재 복용 중으로 등록된" in report.report_markdown
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/schemas/test_intake_report_schema.py -q`

Expected: `scheduled_slots`와 `IntakeReportResult`가 없어 실패한다.

- [ ] **Step 3: Provider가 slot 관계를 prefetch하고 Schema에 기본 빈 목록을 추가한다.**

```python
class ActiveMedication(BaseModel):
    # 기존 필드 유지
    scheduled_slots: list[str] = Field(default_factory=list)


class ActiveSupplement(BaseModel):
    # 기존 필드 유지
    scheduled_slots: list[str] = Field(default_factory=list)


medication_rows = await Medication.filter(...).prefetch_related("slots")
supplement_rows = await UserSupplementNutrient.filter(...).prefetch_related(
    "supplement_nutrient", "slots"
)


scheduled_slots = sorted(slot.slot.value for slot in medication.slots)
```

`intake_report.py`에는 다음 열거형과 결과 모델을 구현한다. `extra="forbid"`와 명확한 기본값을 사용한다.

```python
class IntakeReportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"


class IntakeReportReviewCardType(StrEnum):
    INTERACTION = "INTERACTION"
    REDUNDANCY = "REDUNDANCY"
    CAUTION = "CAUTION"
    MISSING_INFO = "MISSING_INFO"


class IntakeReportResult(BaseModel):
    status: IntakeReportStatus
    data_availability: IntakeReportDataAvailability
    executive_summary: IntakeReportExecutiveSummary
    current_stack: list[IntakeReportCurrentStackItem] = Field(default_factory=list)
    review_cards: list[IntakeReportReviewCard] = Field(default_factory=list)
    nutrient_totals: list[IntakeReportNutrientTotal] = Field(default_factory=list)
    chart_data: IntakeReportChartData
    product_guides: list[IntakeReportProductGuide] = Field(default_factory=list)
    unverified_items: list[IntakeReportUnverifiedItem] = Field(default_factory=list)
    report_markdown: str = Field(min_length=1)
```

- [ ] **Step 4: 단위 테스트를 통과시킨다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/schemas/test_intake_report_schema.py -q`

Expected: PASS

- [ ] **Step 5: 커밋한다.**

```bash
git add ai_worker/schemas/medication_chat.py ai_worker/providers/db_active_intake_context_provider.py ai_worker/schemas/intake_report.py ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/schemas/test_intake_report_schema.py
git commit -m "[feature/311][임경수] 보고서 활성 복용정보 계약 추가"
```

## Task 2: 결정론적 보고서 조립기와 근거 카드

**Files:**
- Create: `ai_worker/assemblers/intake_report_assembler.py`
- Create: `ai_worker/tests/assemblers/test_intake_report_assembler.py`
- Modify: `ai_worker/llm/assemblers/__init__.py`

**Interfaces:**
- Consumes: `ActiveIntakeContext`, `list[MedicationGuideLookup]`, `list[InteractionRuleFact]`, `list[RetrievedKnowledgeChunk]`
- Produces: `IntakeReportDraft`

- [ ] **Step 1: 카드·표·미확인 항목의 실패 테스트를 작성한다.**

```python
def test_assembler_prioritizes_approved_interaction_rules() -> None:
    draft = IntakeReportAssembler().assemble(
        context=active_context,
        guide_lookups=[],
        approved_rules=[approved_rule],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.review_cards[0].card_type == IntakeReportReviewCardType.INTERACTION
    assert draft.review_cards[0].evidence_level == IntakeReportEvidenceLevel.APPROVED_RULE
    assert draft.executive_summary.interaction_check_count == 1


def test_assembler_marks_missing_amount_without_total() -> None:
    draft = IntakeReportAssembler().assemble(
        context=context_with_unknown_supplement_amount,
        guide_lookups=[],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.nutrient_totals == []
    assert draft.unverified_items[0].item_type == IntakeReportUnverifiedItemType.MISSING_AMOUNT
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/assemblers/test_intake_report_assembler.py -q`

Expected: `IntakeReportAssembler`가 없어 실패한다.

- [ ] **Step 3: 결정론적 조립기를 구현한다.**

다음 규칙을 코드로 고정한다.

```python
def assemble(...)-> IntakeReportDraft:
    current_stack = self._current_stack(context, guide_lookups)
    interaction_cards = self._interaction_cards(approved_rules)
    missing_info_cards = self._missing_info_cards(context, guide_lookups)
    cards = self._prioritize([*interaction_cards, *missing_info_cards])
    return IntakeReportDraft(
        current_stack=current_stack,
        review_cards=cards,
        nutrient_totals=[],  # 완전한 성분별 일일 함량 계약이 확인되기 전에는 계산하지 않음
        unverified_items=self._unverified_items(...),
        sources=self._sources(...),
        deterministic_markdown=self._render_markdown(...),
    )
```

- 제품 목록은 의약품·영양제 순서와 ID 순서를 유지한다.
- 승인 규칙 카드는 `DRUG_DRUG`, `DRUG_SUPPLEMENT`, `SUPPLEMENT_SUPPLEMENT`, `DRUG_FOOD` 순서를 유지한다.
- 상호작용 규칙이 없을 때 “안전함” 카드를 만들지 않는다.
- 제품 가이드가 모호하면 후보 제품명을 `MISSING_INFO` 카드에 넣고 일반 제품 안내를 사실처럼 출력하지 않는다.
- `nutrient_totals`는 이번 Task에서 빈 목록으로 유지하고, 성분 단위·1회 함량·일일 횟수 계약이 정규화된 후 별도 기능으로 확장한다.
- fallback Markdown은 `docs/intake-report-output-template.md`의 섹션을 따르되, 비어 있는 02·04·05·06·07 섹션을 출력하지 않는다.

- [ ] **Step 4: 단위 테스트를 통과시킨다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/assemblers/test_intake_report_assembler.py -q`

Expected: PASS

- [ ] **Step 5: 커밋한다.**

```bash
git add ai_worker/assemblers/intake_report_assembler.py ai_worker/llm/assemblers/__init__.py ai_worker/tests/assemblers/test_intake_report_assembler.py
git commit -m "[feature/311][임경수] 보고서 근거 카드 조립기 추가"
```

## Task 3: 보고서 전용 Markdown 체인·프롬프트·안전성 검증

**Files:**
- Create: `ai_worker/chains/intake_report_chain.py`
- Create: `ai_worker/llm/generators/intake_report_generator.py`
- Create: `ai_worker/llm/prompts/intake_report_prompt.py`
- Create: `ai_worker/llm/prompts/assets/intake_report_prompt_v1.md`
- Modify: `ai_worker/llm/prompts/prompt_assets.py`
- Create: `ai_worker/safety/intake_report_validator.py`
- Create: `ai_worker/tests/chains/test_intake_report_chain.py`
- Create: `ai_worker/tests/llm/generators/test_intake_report_generator.py`
- Create: `ai_worker/tests/safety/test_intake_report_validator.py`

**Interfaces:**
- Produces: `IntakeReportMarkdownPayload(report_markdown: str)`
- Produces: `OpenAIIntakeReportGenerator.generate(draft: IntakeReportDraft) -> IntakeReportGenerationOutcome`
- Produces: `IntakeReportGroundingValidator.validate(generated_markdown, draft) -> str | None`

- [ ] **Step 1: 금지 복용 지시와 fallback의 실패 테스트를 작성한다.**

```python
def test_validator_rejects_new_dosage_change_instruction() -> None:
    markdown = "## 안내\n- 마그네슘을 하루 2회로 늘리세요."

    assert IntakeReportGroundingValidator().validate(
        generated_markdown=markdown,
        draft=draft,
    ) is None


@pytest.mark.asyncio
async def test_generator_returns_deterministic_markdown_after_validation_failure() -> None:
    generator = OpenAIIntakeReportGenerator(
        model="test-model",
        client=UnsafeReportClient(),
    )

    outcome = await generator.generate(draft=draft)

    assert outcome.fallback_used is True
    assert outcome.report_markdown == draft.deterministic_markdown
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/chains/test_intake_report_chain.py ai_worker/tests/llm/generators/test_intake_report_generator.py ai_worker/tests/safety/test_intake_report_validator.py -q`

Expected: 새로운 체인·Generator·Validator가 없어 실패한다.

- [ ] **Step 3: LCEL 체인과 Markdown 전용 프롬프트를 구현한다.**

`prompt_assets.py` 허용 목록에 `intake_report_prompt_v1.md`를 추가한다. 프롬프트 문서는 기존 `medication_chat_prompt_v3.md`와 같은 marker 형식을 사용하고, 다음 내용을 명시한다.

```md
### Constraint

1. 입력 초안에 없는 제품·성분·함량·상호작용·효능을 추가하지 않습니다.
2. 복용 시작·중단·증량·감량·복용 간격 변경을 지시하지 않습니다.
3. 근거가 없는 경우 "확인하지 못했습니다"라고 씁니다.
4. 허용 Markdown은 제목, 인용문, 굵게, 목록, 표, 링크뿐입니다.
```

체인은 기존 패턴을 따라 입력 검증 → Prompt 메시지 변환 → `ChatOpenAI.with_structured_output` → 출력 검증으로 구성한다.

```python
return (
    RunnableLambda(_validate_input).with_config(run_name="intake_report.input")
    | RunnableLambda(_build_messages).with_config(run_name="intake_report.prompt")
    | response_runnable
    | RunnableLambda(_validate_payload).with_config(run_name="intake_report.output")
).with_types(
    input_type=IntakeReportChainInput,
    output_type=IntakeReportMarkdownPayload,
)
```

Validator는 다음을 검사한다.

- `<script`, raw HTML tag, 코드 펜스, 허용하지 않은 heading 수준을 차단한다.
- `중단`, `증량`, `감량`, `처방`, `진단`과 직접적인 지시형 문장을 차단한다.
- 초안에 없던 숫자+단위 조합을 차단한다.
- 생성 실패 또는 검증 실패는 예외 대신 `draft.deterministic_markdown` fallback과 관측값으로 반환한다.

- [ ] **Step 4: 체인·Generator·Validator 테스트를 통과시킨다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/chains/test_intake_report_chain.py ai_worker/tests/llm/generators/test_intake_report_generator.py ai_worker/tests/safety/test_intake_report_validator.py -q`

Expected: PASS

- [ ] **Step 5: 커밋한다.**

```bash
git add ai_worker/chains/intake_report_chain.py ai_worker/llm/generators/intake_report_generator.py ai_worker/llm/prompts/intake_report_prompt.py ai_worker/llm/prompts/assets/intake_report_prompt_v1.md ai_worker/llm/prompts/prompt_assets.py ai_worker/safety/intake_report_validator.py ai_worker/tests/chains/test_intake_report_chain.py ai_worker/tests/llm/generators/test_intake_report_generator.py ai_worker/tests/safety/test_intake_report_validator.py
git commit -m "[feature/311][임경수] 보고서 Markdown 안전성 체인 추가"
```

## Task 4: 보고서 UseCase와 AI Worker Core Service

**Files:**
- Create: `ai_worker/use_cases/generate_intake_report.py`
- Create: `ai_worker/services/intake_report_core_service.py`
- Create: `ai_worker/tests/use_cases/test_generate_intake_report.py`
- Create: `ai_worker/tests/services/test_intake_report_core_service.py`

**Interfaces:**
- Produces: `GenerateIntakeReportUseCase.execute(user_id: int) -> IntakeReportResult`
- Produces: `IntakeReportCoreService.generate(user_id: int) -> IntakeReportResult`
- Produces: `build_intake_report_core_service(settings, qdrant_client, tracer) -> IntakeReportCoreService`

- [ ] **Step 1: 정상·빈 목록·RAG 장애 부분 응답의 실패 테스트를 작성한다.**

```python
@pytest.mark.asyncio
async def test_use_case_returns_empty_without_openai_or_qdrant_call() -> None:
    result = await use_case.execute(user_id=1)

    assert result.status == IntakeReportStatus.EMPTY
    assert generator.calls == 0
    assert retriever.calls == 0


@pytest.mark.asyncio
async def test_use_case_returns_partial_when_rag_is_unavailable() -> None:
    result = await unavailable_rag_use_case.execute(user_id=1)

    assert result.status == IntakeReportStatus.PARTIAL
    assert result.data_availability.rag_evidence_available is False
    assert "확인하지 못했습니다" in result.report_markdown
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/use_cases/test_generate_intake_report.py ai_worker/tests/services/test_intake_report_core_service.py -q`

Expected: UseCase와 Core Service가 없어 실패한다.

- [ ] **Step 3: 근거 조회 정책과 UseCase를 구현한다.**

```python
async def execute(self, *, user_id: int) -> IntakeReportResult:
    context = await self._context_provider.get_active_context(
        user_id=user_id,
        care_episode_id=None,
    )
    if not context.medications and not context.supplements:
        return IntakeReportResult.empty(user_id=user_id)

    guide_lookups, approved_rules, knowledge = await self._collect_evidence(context)
    draft = self._assembler.assemble(
        context=context,
        guide_lookups=guide_lookups,
        approved_rules=approved_rules,
        knowledge_chunks=knowledge.chunks,
        rag_available=knowledge.available,
    )
    outcome = await self._generator.generate(draft=draft)
    return draft.to_result(
        report_markdown=outcome.report_markdown,
        status=IntakeReportStatus.PARTIAL if not knowledge.available else IntakeReportStatus.COMPLETED,
    )
```

- 의약품 가이드 조회는 고유한 현재 약 이름에 대해 `asyncio.gather`로 병렬화한다.
- 승인 규칙은 활성 컨텍스트 전체에 대해 한 번만 `find_approved_rules(context=context)`를 호출한다.
- Qdrant는 활성 영양제의 서로 다른 이름을 최대 5개까지 대상으로 하며, 이름마다 `"{name} 기능 주의사항"` QueryPlan을 만들고 결과는 최대 2개 청크로 제한한다.
- Qdrant 예외는 잡아 `rag_available=False`로 기록하되, RDBMS 초안은 계속 생성한다.
- Context Provider·제품 가이드·승인 규칙 Repository가 실패하면 `AIWorkerError`를 발생시켜 API가 503으로 변환하도록 한다.
- 기존 `build_medication_chat_core_service`를 수정하지 않고 동일한 Config·Qdrant·Tracer 구성 방식으로 별도 builder를 만든다.

- [ ] **Step 4: UseCase·Core Service 테스트를 통과시킨다.**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/use_cases/test_generate_intake_report.py ai_worker/tests/services/test_intake_report_core_service.py -q`

Expected: PASS

- [ ] **Step 5: 커밋한다.**

```bash
git add ai_worker/use_cases/generate_intake_report.py ai_worker/services/intake_report_core_service.py ai_worker/tests/use_cases/test_generate_intake_report.py ai_worker/tests/services/test_intake_report_core_service.py
git commit -m "[feature/311][임경수] 활성 복용정보 보고서 UseCase 추가"
```

## Task 5: FastAPI Application Service·DTO·Router 연결

**Files:**
- Create: `app/services/intake_report.py`
- Create: `app/dependencies/intake_report.py`
- Create: `app/dtos/intake_reports.py`
- Create: `app/apis/v1/intake_report_router.py`
- Modify: `app/apis/v1/__init__.py`
- Modify: `app/main.py`
- Modify: `app/core/exceptions.py`
- Create: `app/tests/intake_report_apis/conftest.py`
- Create: `app/tests/intake_report_apis/test_intake_report_api.py`
- Create: `app/tests/intake_report_apis/test_intake_report_service.py`

**Interfaces:**
- Produces: `IntakeReportApplicationService.generate(user: User) -> IntakeReportView`
- Produces: `POST /api/v1/intake-reports`
- Produces: camelCase JSON payload matching the API specification

- [ ] **Step 1: API 계약의 실패 테스트를 작성한다.**

```python
@pytest.mark.asyncio
async def test_generate_intake_report_returns_camel_case_payload(client, user, service) -> None:
    app.dependency_overrides[get_intake_report_application_service] = lambda: service

    response = await client.post(
        "/api/v1/intake-reports",
        headers=auth_headers(user),
        json={},
    )

    assert response.status_code == 200
    assert response.json()["reportStatus"] == "COMPLETED"
    assert response.json()["executiveSummary"]["summaryCards"]


@pytest.mark.asyncio
async def test_generate_intake_report_returns_401_without_token(client) -> None:
    response = await client.post("/api/v1/intake-reports", json={})

    assert response.status_code == 401
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest app/tests/intake_report_apis/test_intake_report_api.py app/tests/intake_report_apis/test_intake_report_service.py -q`

Expected: Router·DTO·Service가 없어 실패한다.

- [ ] **Step 3: Application Service와 Router를 구현한다.**

```python
@intake_report_router.post(
    "",
    response_model=IntakeReportResponse,
    summary="내 복용약·영양제 생활관리 보고서 생성",
    description=(
        "현재 활성 복용약과 영양제를 함께 분석해 성분 중복, 승인된 상호작용 규칙, "
        "제품 안내와 확인 필요 정보를 반환합니다. 진단·처방·복용 변경을 대신하지 않습니다."
    ),
    responses=INTAKE_REPORT_RESPONSES,
)
@api_timeout(INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS)
async def generate_intake_report(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[IntakeReportApplicationService, Depends(get_intake_report_application_service)],
) -> IntakeReportResponse:
    return IntakeReportResponse.from_view(await service.generate(user=user))
```

- `INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS = 30.0`을 Service 모듈에 둔다.
- Service는 `asyncio.timeout(30.0)` 안에서 Core Service를 호출하고, `ChatTracer`의 새 root span `intake-report.generate`에 hash된 `user_key`, 활성 제품 수, 카드 수, source 수, status, duration을 기록한다.
- `app.state.intake_report_qdrant_client`와 `app.state.intake_report_application_service`를 사용한다. Chat Qdrant Client와 공유하지 않아 종료 순서와 생성 책임이 충돌하지 않게 한다.
- `lifespan`은 report Qdrant client·tracer도 닫는다.
- `IntakeReportUpstreamUnavailableError`(503)와 `IntakeReportTimeoutError`(504)를 `AppError`로 추가한다.
- Response DTO는 Pydantic `CamelModel`로 구현해 `reportStatus`, `dataAvailability`, `executiveSummary`, `currentStack`, `reviewCards`, `nutrientTotals`, `chartData`, `productGuides`, `unverifiedItems`, `reportMarkdown`을 만든다.
- Router는 `app.apis.v1.__init__.py`에서 `chat_router` 뒤에 등록한다.

- [ ] **Step 4: API·Service 테스트를 통과시킨다.**

Run: `uv run --group ai --group app --group dev python -m pytest app/tests/intake_report_apis -q`

Expected: PASS

- [ ] **Step 5: 커밋한다.**

```bash
git add app/services/intake_report.py app/dependencies/intake_report.py app/dtos/intake_reports.py app/apis/v1/intake_report_router.py app/apis/v1/__init__.py app/main.py app/core/exceptions.py app/tests/intake_report_apis
git commit -m "[feature/311][임경수] 복용 정보 보고서 API 추가"
```

## Task 6: ReDoc·통합 회귀 검증·문서 동기화

**Files:**
- Modify: `docs/intake-report-output-template.md` only if implementation contracts require a factual correction
- Modify: `docs/superpowers/specs/2026-09-08-intake-report-api-design.md` only if implementation contracts require a factual correction
- Create: `app/tests/intake_report_apis/test_intake_report_runtime.py`
- Create: `ai_worker/tests/integration/test_intake_report_openai_integration.py`

**Interfaces:**
- Verifies: `/api/redoc`의 summary·description·200/401/503/504 계약
- Verifies: 실제 OpenAI는 선택적 통합 테스트에서만 호출

- [ ] **Step 1: ReDoc과 부분 응답의 실패 테스트를 작성한다.**

```python
def test_openapi_describes_intake_report_endpoint(app) -> None:
    operation = app.openapi()["paths"]["/api/v1/intake-reports"]["post"]

    assert operation["summary"] == "내 복용약·영양제 생활관리 보고서 생성"
    assert {"200", "401", "503", "504"}.issubset(operation["responses"])


@pytest.mark.asyncio
async def test_rag_failure_keeps_structured_rdbms_report(...) -> None:
    response = await client.post("/api/v1/intake-reports", headers=auth_headers(user), json={})

    assert response.status_code == 200
    assert response.json()["reportStatus"] == "PARTIAL"
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `uv run --group ai --group app --group dev python -m pytest app/tests/intake_report_apis/test_intake_report_runtime.py -q`

Expected: ReDoc 계약 또는 부분 응답이 누락돼 실패한다.

- [ ] **Step 3: 누락된 OpenAPI 예시와 통합 테스트를 구현한다.**

- Router `responses`에 200의 최소 카드·표 응답 예시와 401·503·504의 한국어 예시를 명시한다.
- OpenAI 통합 테스트는 `RUN_OPENAI_INTEGRATION_TESTS=true`일 때만 실행하도록 skip marker를 둔다.
- 통합 결과에서 `report_markdown`이 한국어 제목을 포함하고 금지 HTML·코드 펜스가 없으며, `review_cards`의 출처가 실제 source 목록에 존재하는지 검증한다.

- [ ] **Step 4: 관련 테스트와 전체 정적 검사를 통과시킨다.**

Run:

```bash
uv run --group dev ruff format . --check
uv run --group dev ruff check ai_worker app
uv run --group ai --group app --group dev python -m pytest ai_worker/tests app/tests/chat_apis app/tests/intake_report_apis -q
git diff --check
```

Expected: 모든 명령이 성공한다.

- [ ] **Step 5: 구현 중 문서 계약이 달라졌을 때만 문서를 갱신하고 커밋한다.**

```bash
git add docs/intake-report-output-template.md docs/superpowers/specs/2026-09-08-intake-report-api-design.md app/tests/intake_report_apis/test_intake_report_runtime.py ai_worker/tests/integration/test_intake_report_openai_integration.py
git commit -m "[feature/311][임경수] 보고서 API 통합 계약 검증"
```

## Plan Self-Review

### Spec coverage

- 별도 Router·DTO·Application Service·Core Service: Task 4, Task 5
- 카드·표·차트·Markdown 응답: Task 1, Task 2, Task 5
- 승인 규칙 우선, Qdrant 보조, RAG 부분 실패: Task 2, Task 4, Task 6
- LLM 구조화 출력·Markdown·안전성 fallback: Task 3
- `EMPTY`, `PARTIAL`, 401·503·504: Task 4, Task 5, Task 6
- ReDoc·LangSmith·30초 제한: Task 5, Task 6
- 채팅·세션·DB 마이그레이션 비변경: 모든 Task의 Global Constraints

### Placeholder scan

`TODO`, `TBD`, "implement later" 같은 미결정 표기를 사용하지 않았다. 영양성분 합산은 현재 단위·함량·횟수 계약이 불완전하므로, 이번 구현에서 명시적으로 빈 목록과 정보 부족 카드로 처리한다.

### Type consistency

- AI Worker는 `IntakeReportResult`를 만들고, Application Service는 이를 `IntakeReportView`로 변환하며, DTO는 `IntakeReportResponse`로 camelCase 직렬화한다.
- Generator는 `IntakeReportDraft`를 입력받아 `IntakeReportGenerationOutcome`을 반환하고, UseCase가 최종 `IntakeReportResult`에 반영한다.
- Router는 `get_intake_report_application_service`로 `IntakeReportApplicationService`만 의존한다.
