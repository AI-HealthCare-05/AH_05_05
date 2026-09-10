# Three-Stage Question Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add an opt-in, safety-preserving question routing layer that uses strict rules first, a local semantic router for uncertain phrasing, and structured LLM fallback only when required.

**Architecture:** The existing resolver still establishes catalog-backed candidates before any semantic decision. A new router only proposes a chat route with an auditable confidence score; it never creates entities or determines medical risk. The existing \`MedicationQueryPlanChain\`, approved-rule lookup, RAG retrieval, and safety policy remain final authorities.

**Tech Stack:** Python 3.13, Pydantic v2, LangChain LCEL, sentence-transformers, CPU PyTorch, pytest, LangSmith metadata.

**Spec:** \`docs/superpowers/specs/2026-09-10-three-stage-question-classification-design.md\`

## Global Constraints

**Execution status (2026-09-10):** Tasks 1–5의 코드·테스트·환경 예시·기준선 기록을 구현했다. SEMANTIC_ROUTER_ENABLED=false와 CONDITIONAL_QUESTION_INTERPRETATION_ENABLED=false를 유지하며, AWS 환경에서 모델을 이미지에 포함한 뒤 고정 평가 세트와 지연시간 측정을 통과해야 활성화한다.

- Never allow Router or LLM output to introduce a product, ingredient, food, or safety rule outside catalog candidates.
- Never retain or trace free-form LLM reasoning / CoT.
- Preserve rule-based resolution as the default; new behavior must be disabled unless configuration enables it.
- Apply safety after routing; existing safety outcomes remain authoritative.
- Do not promise 10–20 ms. Record Router latency and activate only after evaluation.
- Do not introduce Tool Calling or LangGraph for this feature.

---

### Task 1: Routing contracts and configuration

**Files:**
- Create: \`ai_worker/chains/semantic_question_router.py\`
- Modify: \`ai_worker/core/config.py\`
- Modify: \`ai_worker/tests/core/test_core_package.py\`
- Test: \`ai_worker/tests/chains/test_semantic_question_router.py\`

**Interfaces:**
- Produce \`QuestionRoutingStage\`, \`QuestionRoutingReasonCode\`, \`QuestionRoutingDecision\`, \`SemanticRouterInput\`, and \`SemanticQuestionRouter\`.
- \`QuestionRoutingDecision\` contains \`route: MedicationChatRoute | None\`, \`confidence\`, \`top_score\`, \`second_score\`, \`reason_codes\`, and \`stage\`.
- Add disabled defaults: \`SEMANTIC_ROUTER_ENABLED\`, \`SEMANTIC_ROUTER_MODEL\`, \`SEMANTIC_ROUTER_MIN_SCORE\`, \`SEMANTIC_ROUTER_MIN_MARGIN\`.

- [ ] **Step 1: Write the failing tests**

~~~python
def test_semantic_router_settings_default_to_disabled() -> None:
    settings = Config(_env_file=None)
    assert settings.SEMANTIC_ROUTER_ENABLED is False
    assert settings.SEMANTIC_ROUTER_MIN_SCORE == 0.78
    assert settings.SEMANTIC_ROUTER_MIN_MARGIN == 0.10


def test_routing_decision_rejects_reasoning() -> None:
    with pytest.raises(ValueError):
        QuestionRoutingDecision.model_validate({
            "stage": "SEMANTIC",
            "route": "INTERACTION",
            "confidence": "HIGH",
            "reasoning": "hidden chain of thought",
        })
~~~

- [ ] **Step 2: Verify RED**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_semantic_question_router.py ai_worker/tests/core/test_core_package.py -q\`
Expected: import or missing-setting failure.

- [ ] **Step 3: Implement the smallest contract**

~~~python
class QuestionRoutingStage(StrEnum):
    RULE = "RULE"
    SEMANTIC = "SEMANTIC"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


class QuestionRoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: QuestionRoutingStage
    route: MedicationChatRoute | None = None
    confidence: MedicationQuestionConfidence
    top_score: float | None = None
    second_score: float | None = None
    reason_codes: list[QuestionRoutingReasonCode] = Field(default_factory=list)
~~~

- [ ] **Step 4: Verify GREEN**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_semantic_question_router.py ai_worker/tests/core/test_core_package.py -q\`
Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add ai_worker/chains/semantic_question_router.py ai_worker/core/config.py ai_worker/tests/chains/test_semantic_question_router.py ai_worker/tests/core/test_core_package.py
git commit -m "feat(ai): add semantic question routing contracts"
~~~

### Task 2: Catalog-safe local Semantic Router

**Files:**
- Modify: \`ai_worker/chains/semantic_question_router.py\`
- Modify: \`ai_worker/tests/chains/test_semantic_question_router.py\`

**Interfaces:**
- \`SemanticRouterInput(question, candidate_count, has_session_reference)\`
- \`QuestionEmbeddingModel.encode(list[str]) -> list[list[float]]\`
- \`LocalSemanticQuestionRouter.ainvoke(input) -> QuestionRoutingDecision\`
- Intent prototypes contain only route examples and never drug/product vocabulary.

- [ ] **Step 1: Write failing threshold/margin tests**

~~~python
async def test_router_accepts_clear_interaction_when_score_and_margin_pass() -> None:
    router = LocalSemanticQuestionRouter(
        embedder=StaticEmbeddingModel([[1, 0], [1, 0], [0, 1], [-1, 0]]),
        min_score=0.78,
        min_margin=0.10,
    )
    decision = await router.ainvoke(SemanticRouterInput(question="같이 먹어도 돼?"))
    assert decision.stage is QuestionRoutingStage.SEMANTIC
    assert decision.route is MedicationChatRoute.INTERACTION


async def test_router_falls_back_when_top_two_routes_are_too_close() -> None:
    router = LocalSemanticQuestionRouter(embedder=StaticEmbeddingModel(...), min_score=0.78, min_margin=0.10)
    decision = await router.ainvoke(SemanticRouterInput(question="애매한 질문"))
    assert decision.stage is QuestionRoutingStage.FALLBACK
    assert decision.route is None
~~~

- [ ] **Step 2: Verify RED**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_semantic_question_router.py -q\`
Expected: \`LocalSemanticQuestionRouter\` is missing or produces an invalid decision.

- [ ] **Step 3: Implement Router and model adapter**

Implement cosine scoring; accept a route only if both score and top-two margin pass. Use an injectable embedder for tests. Add a lazy process-local SentenceTransformer adapter that never downloads during a request and raises a configuration error when the packaged model is unavailable.

- [ ] **Step 4: Verify GREEN**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_semantic_question_router.py -q\`
Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add ai_worker/chains/semantic_question_router.py ai_worker/tests/chains/test_semantic_question_router.py
git commit -m "feat(ai): add local semantic question router"
~~~

### Task 3: Safely merge semantic decisions in the chat use case

**Files:**
- Modify: \`ai_worker/use_cases/answer_medication_question.py\`
- Modify: \`ai_worker/tests/use_cases/test_answer_medication_question.py\`

**Interfaces:**
- \`AnswerMedicationQuestionUseCase(..., semantic_question_router: SemanticQuestionRouter | None = None)\`
- Emit \`query.plan.semantic_router\` with decision stage, route, score/margin, candidate count, and elapsed time.
- Produce the existing \`MedicationQuestionPlanResult\`; the Router adds no entities, sections, or interaction pairs.

- [ ] **Step 1: Write failing integration tests**

~~~python
async def test_execute_uses_semantic_route_only_after_uncertain_rule_plan() -> None:
    router = RecordingSemanticRouter(
        QuestionRoutingDecision.semantic(MedicationChatRoute.INTERACTION, 0.91, 0.52),
    )
    result = await build_use_case(semantic_question_router=router).execute(
        build_request("마그네슘이랑 아연 가치 먹어도 돼?"),
    )
    assert router.inputs
    assert result.route is MedicationChatRoute.INTERACTION


async def test_execute_does_not_allow_semantic_product_route_without_catalog_entity() -> None:
    router = RecordingSemanticRouter(
        QuestionRoutingDecision.semantic(MedicationChatRoute.MEDICATION_GUIDE, 0.95, 0.30),
    )
    result = await build_use_case(semantic_question_router=router).execute(build_request("피곤해"))
    assert result.route is not MedicationChatRoute.MEDICATION_GUIDE
~~~

- [ ] **Step 2: Verify RED**

Run: \`uv run --group ai pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k semantic_router -q\`
Expected: constructor does not accept the Router.

- [ ] **Step 3: Implement safe invocation and merge**

Call the Router only after resolver/query-plan output exists and only when the rule plan is not a high-confidence terminal outcome. Keep greeting, out-of-scope, clarification, explicit safety blocks, and fatigue triage on their existing paths. A semantic route only selects a compatible existing route.

- [ ] **Step 4: Verify GREEN**

Run: \`uv run --group ai pytest ai_worker/tests/use_cases/test_answer_medication_question.py -q\`
Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add ai_worker/use_cases/answer_medication_question.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "feat(ai): route ambiguous questions through semantic classifier"
~~~

### Task 4: Candidate-key structured LLM fallback

**Files:**
- Modify: \`ai_worker/chains/conditional_question_interpretation_chain.py\`
- Modify: \`ai_worker/use_cases/answer_medication_question.py\`
- Modify: \`ai_worker/tests/chains/test_conditional_question_interpretation_chain.py\`
- Modify: \`ai_worker/tests/use_cases/test_answer_medication_question.py\`

**Interfaces:**
- Input sends a server-created \`candidate_key -> MedicationQueryEntity\` map.
- Output returns \`route\`, \`candidate_entity_keys\`, allowed sections, confidence, and reason codes.
- Output never contains free-form entity names or reasoning.
- Use case ignores unknown keys and unsupported routes.

- [ ] **Step 1: Write failing schema tests**

~~~python
def test_llm_output_accepts_candidate_keys_and_route() -> None:
    output = ConditionalQuestionInterpretationOutput(
        route="INTERACTION",
        candidate_entity_keys=["candidate_0", "candidate_1"],
        requested_section_types=[KnowledgeSectionType.INTERACTION],
        confidence="MEDIUM",
        reason_codes=["MULTI_ENTITY"],
    )
    assert output.candidate_entity_keys == ["candidate_0", "candidate_1"]


def test_llm_output_rejects_free_form_entity_name() -> None:
    with pytest.raises(ValueError):
        ConditionalQuestionInterpretationOutput.model_validate({
            "route": "INTERACTION",
            "candidate_entity_keys": [],
            "canonical_entity_names": ["invented medicine"],
            "confidence": "LOW",
        })
~~~

- [ ] **Step 2: Verify RED**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py -k conditional -q\`
Expected: new schema fields are rejected or obsolete free-form names are accepted.

- [ ] **Step 3: Implement strict key validation**

Render only candidate key/name pairs in the prompt. Validate returned keys against the active candidate map. Keep section additions restricted to \`FUNCTION\`, \`DAILY_INTAKE\`, \`CAUTION\`, and \`INTERACTION\`. Preserve current LLM provider-failure fallback.

- [ ] **Step 4: Verify GREEN**

Run: \`uv run --group ai pytest ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py -q\`
Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add ai_worker/chains/conditional_question_interpretation_chain.py ai_worker/use_cases/answer_medication_question.py ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "feat(ai): validate conditional LLM routes by candidate key"
~~~

### Task 5: Opt-in dependency injection and evaluation record

**Files:**
- Modify: \`ai_worker/services/medication_chat_core_service.py\`
- Modify: \`ai_worker/tests/services/test_medication_chat_core_service.py\`
- Modify: \`.env.example\`
- Create: \`docs/superpowers/experiments/2026-09-10-question-routing-baseline.md\`

**Interfaces:**
- \`build_medication_chat_core_service()\` creates the Router only when \`SEMANTIC_ROUTER_ENABLED=true\`.
- Router setup errors preserve the disabled/default rule-only path rather than breaking chat startup.
- The evaluation document lists the fixed questions, route accuracy, wrong-entity rate, safety regression count, fallback rate, and Router/total P50/P95.

- [ ] **Step 1: Write failing service tests**

~~~python
def test_builder_does_not_construct_router_when_disabled() -> None:
    service = build_medication_chat_core_service(
        settings=Config(OPENAI_API_KEY="test-key", SEMANTIC_ROUTER_ENABLED=False, _env_file=None),
        qdrant_client=object(),
    )
    assert service._use_case._semantic_question_router is None


def test_builder_constructs_router_when_enabled() -> None:
    service = build_medication_chat_core_service(
        settings=Config(OPENAI_API_KEY="test-key", SEMANTIC_ROUTER_ENABLED=True, _env_file=None),
        qdrant_client=object(),
    )
    assert service._use_case._semantic_question_router is not None
~~~

- [ ] **Step 2: Verify RED**

Run: \`uv run --group ai pytest ai_worker/tests/services/test_medication_chat_core_service.py -k semantic_router -q\`
Expected: Router wiring does not exist.

- [ ] **Step 3: Wire configuration and document the baseline**

Use configured model/thresholds. Add disabled example values to \`.env.example\`. Create the experiment record with result fields but do not claim measured values until the user runs the fixed evaluation set.

- [ ] **Step 4: Verify GREEN**

Run: \`uv run --group ai pytest ai_worker/tests/services/test_medication_chat_core_service.py -q && uv run --group ai ruff check ai_worker && uv run --group ai ruff format ai_worker --check\`
Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add ai_worker/services/medication_chat_core_service.py ai_worker/tests/services/test_medication_chat_core_service.py .env.example docs/superpowers/experiments/2026-09-10-question-routing-baseline.md
git commit -m "feat(ai): wire opt-in semantic question routing"
~~~

### Task 6: Final verification and implementation status

**Files:**
- Modify: \`docs/superpowers/specs/2026-09-10-three-stage-question-classification-design.md\`
- Modify: \`docs/superpowers/plans/2026-09-10-three-stage-question-classification.md\`

- [ ] **Step 1: Run full AI Worker tests**

Run: \`uv run --group ai pytest ai_worker/tests -q\`
Expected: PASS.

- [ ] **Step 2: Run repository static checks**

Run: \`uv run --group ai ruff check . && uv run --group ai ruff format . --check\`
Expected: PASS.

- [ ] **Step 3: Record actual implementation status**

Update the spec history and plan checkboxes. State that \`SEMANTIC_ROUTER_ENABLED\` remains false until AWS latency and fixed-question evaluation have recorded results.

- [ ] **Step 4: Commit**

~~~bash
git add docs/superpowers/specs/2026-09-10-three-stage-question-classification-design.md docs/superpowers/plans/2026-09-10-three-stage-question-classification.md
git commit -m "docs(ai): record question routing implementation status"
~~~

## Execution Record

- [x] Task 1: Router 계약과 비활성 기본 설정
- [x] Task 2: 점수·마진 기반 로컬 Semantic Router 및 로컬 모델 어댑터
- [x] Task 3: 기존 Query Plan·안전성 정책을 우회하지 않는 UseCase 병합
- [x] Task 4: 후보 키 전용 구조화 LLM fallback v2
- [x] Task 5: feature flag 의존성 주입, 환경 예시, 고정 평가 기준선 문서
- [x] Task 6: AI Worker 전체 pytest 및 Ruff 전체 검증
