# Medication Chat Prompt Chain v7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with RED → GREEN verification and path-limited commits.

**Goal:** 확정된 v7 명세를 사람이 수정할 수 있는 단일 런타임 프롬프트 팩, 구조화 Pydantic 계약, 조건부 LCEL 체인으로 구현하고 기존 검색·안전 경계를 유지한다.

**Architecture:** 규칙 기반 Resolver와 Semantic Router 뒤에서 낮은 신뢰도·복수 엔터티·세션 참조 질문만 Directional Query 체인을 사용한다. RDBMS·APPROVED 규칙·Qdrant Exact-pair/Entity/Semantic, Small-to-Big, 근거 부족 시 최대 1회 재검색은 그대로 유지한다. 상호작용 근거가 존재할 때만 선택적으로 Evidence Reasoning 체인을 호출하며, 결과는 서버가 후보 키와 evidence ID를 다시 검증한 뒤 최종 답변 프롬프트에 전달한다. 모든 LLM 실패는 기존 결정론적 분류·검색·답변 초안으로 복귀한다.

**Tech Stack:** Python 3.14, Pydantic v2, LangChain LCEL, ChatOpenAI structured output, pytest, Ruff

**Spec:** `docs/prompts/medication-chat-prompt-chain-v7.md`

## Global Constraints

- `medication_chat_prompt_v7.md` 한 파일에 공통 규칙과 단계별 구역을 두고, 런타임은 필요한 구역만 로드한다.
- 각 stage는 `Role`, `Task`, `Content`, `Format`, `Constraint`, `Example` 6요소를 명시하며 공통 제약은 중복하지 않는다.
- 의료 사실·제품명·성분명·pair key·evidence ID는 서버가 제공한 후보 밖에서 생성하거나 채택하지 않는다.
- 내부 추론 원문(CoT)은 모델 출력, Trace, DB, API 응답에 저장하지 않는다.
- Conversation Gate의 진료일정·복약메모 분기와 기존 프론트 고정 면책 문구 정책을 유지한다.
- Qdrant 검색 tier, Small-to-Big, coverage retry, GroundedClaimValidator를 교체하거나 우회하지 않는다.
- `INTERACTION_EVIDENCE_REASONING_ENABLED` 기본값은 `false`이며 고정 평가 전에는 런타임 활성화하지 않는다.
- 기존 사용자 파일 `docs/superpowers/chatbot-architecture-current-v2.html`과 `media/ocr-tmp/*`는 수정·스테이징하지 않는다.

## Task 1: v7 명세와 실행 계약 확정

**Files:**

- Add: `docs/prompts/medication-chat-prompt-chain-v7.md`
- Add: `docs/superpowers/plans/2026-09-12-medication-chat-prompt-chain-v7.md`

**Step 1: 명세 정합성을 검사한다**

- 모든 `json` 코드 블록을 파싱한다.
- `conversation_gate`, `directional_query`, `evidence_reasoning`, `answer_generation`, `conversation_response`, `medication_note_summary`의 system/user/examples 마커가 한 쌍씩인지 확인한다.
- `TODO`, `TBD`, 이전 v6 버전명이 남아 있지 않은지 확인한다.

**Step 2: 기존 기준선 테스트를 실행한다**

Run:

```bash
uv run pytest ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/chains/test_conversation_gate_chain.py -q
```

Expected: 27 tests pass.

**Step 3: 문서만 경로 지정해 커밋한다**

```bash
git add docs/prompts/medication-chat-prompt-chain-v7.md docs/superpowers/plans/2026-09-12-medication-chat-prompt-chain-v7.md
git commit -m "docs(ai): finalize medication prompt chain v7"
```

## Task 2: 단계별 런타임 프롬프트 팩과 로더

**Files:**

- Create: `ai_worker/llm/prompts/assets/medication_chat_prompt_v7.md`
- Modify: `ai_worker/llm/prompts/prompt_assets.py`
- Create: `ai_worker/tests/llm/prompts/test_prompt_chain_assets.py`

**Step 1: 실패 테스트를 작성한다**

테스트가 잡아야 할 결함:

- 허용되지 않은 stage가 조용히 빈 문자열로 로드됨
- stage marker가 없거나 중복돼도 잘못된 프롬프트가 실행됨
- 공통 규칙과 stage별 규칙이 결합되지 않음
- 한 stage를 읽을 때 다른 stage의 사용자 템플릿이 섞임

추가할 계약:

```python
class MedicationPromptStage(StrEnum): ...

@dataclass(frozen=True)
class PromptChainStageDocument:
    common: str
    system: str
    user: str
    examples: str

    @property
    def compiled_system(self) -> str: ...

def load_prompt_chain_stage(asset_name: str, stage: MedicationPromptStage) -> PromptChainStageDocument: ...
```

Run:

```bash
uv run pytest ai_worker/tests/llm/prompts/test_prompt_chain_assets.py -q
```

Expected RED: import 또는 marker parser 부재로 실패.

**Step 2: 최소 로더와 v7 프롬프트 팩을 구현한다**

- `common:system`은 후보 제한, 근거 제한, 비노출 추론, 구조화 출력 원칙만 가진다.
- 각 stage는 자신이 담당하는 판단과 입력 placeholder만 가진다.
- `examples`는 해당 stage system prompt 뒤에 결합하되 사용자 입력 템플릿에는 섞지 않는다.
- 기존 v1~v6 자산과 `load_prompt_template_document`는 롤백 호환을 위해 유지한다.

**Step 3: GREEN과 회귀 테스트를 실행한다**

```bash
uv run pytest ai_worker/tests/llm/prompts/test_prompt_chain_assets.py ai_worker/tests/llm/prompts/test_medication_chat_prompt.py -q
```

**Step 4: 커밋한다**

```bash
git add ai_worker/llm/prompts/assets/medication_chat_prompt_v7.md ai_worker/llm/prompts/prompt_assets.py ai_worker/tests/llm/prompts/test_prompt_chain_assets.py
git commit -m "feat(ai): load stage-aware medication prompt pack"
```

## Task 3: Directional Query 구조화 해석 체인

**Files:**

- Modify: `ai_worker/chains/conditional_question_interpretation_chain.py`
- Modify: `ai_worker/tests/chains/test_conditional_question_interpretation_chain.py`
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Step 1: 출력 경계 실패 테스트를 작성한다**

테스트가 잡아야 할 결함:

- 입력 후보 밖의 entity key 또는 pair key 채택
- 허용 검색어와 무관한 의학적 주장을 stimulus query에 추가
- `효능과 주의사항`을 상호작용으로 바꾸거나 section 하나를 버림
- clarification인데 질문 문구가 없거나, clarification이 아닌데 임의 질문 문구를 생성

구조화 모델:

```python
class DirectionalSearchTarget(StrEnum): ...

class DirectionalSearchStimulus(BaseModel):
    query: str
    target: DirectionalSearchTarget
    section_types: list[KnowledgeSectionType]
    purpose: str
```

`ConditionalQuestionInterpretationInput`에는 `candidate_pair_keys`, `allowed_search_terms`, `session_reference_entities`, `current_query_plan`을 추가한다. Output에는 `normalized_question`, `interaction_pair_keys`, `stimuli`, `needs_clarification`, `clarification_question`을 추가한다.

Run:

```bash
uv run pytest ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py -q
```

Expected RED: 신규 필드·검증 부재로 실패.

**Step 2: v7 directional stage를 사용해 체인을 구현한다**

- Prompt 문자열을 Python에서 제거하고 v7 stage loader로 읽는다.
- LCEL 출력 뒤 서버 검증에서 entity/pair key를 입력 집합과 교차 검증한다.
- stimulus query는 허용 검색어 중 하나 이상과 검증된 entity 정식명을 포함한 경우만 채택한다.
- 검증된 stimulus는 기존 `alternate_queries`에 추가하고 기존 Query Plan 필드는 유지한다.
- 모델 오류·모든 stimulus 폐기 시 원래 planning을 그대로 반환한다.

**Step 3: GREEN과 회귀 테스트를 실행한다**

```bash
uv run pytest ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py -q
```

**Step 4: 커밋한다**

```bash
git add ai_worker/chains/conditional_question_interpretation_chain.py ai_worker/use_cases/answer_medication_question.py ai_worker/tests/chains/test_conditional_question_interpretation_chain.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "feat(ai): add bounded directional query interpretation"
```

## Task 4: Evidence Reasoning Pydantic 계약과 LCEL 체인

**Files:**

- Create: `ai_worker/schemas/evidence_reasoning.py`
- Create: `ai_worker/chains/interaction_evidence_reasoning_chain.py`
- Create: `ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py`

**Step 1: 실패 테스트를 작성한다**

테스트가 잡아야 할 결함:

- 입력에 없는 evidence ID로 주장 생성
- 직접 관계 근거 없이 `INTERACTION_CONFIRMED` 반환
- 자유 형식 `reasoning`/CoT 필드 출력 허용
- 충돌 판정에 실제 conflict evidence ID가 없음
- `NOT_APPLICABLE`을 상호작용 요청에 사용

핵심 계약:

```python
class InteractionEvidenceDecision(StrEnum):
    INTERACTION_CONFIRMED = "INTERACTION_CONFIRMED"
    NO_DIRECT_EVIDENCE = "NO_DIRECT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class EvidenceReasoningOutput(BaseModel):
    reasoning_status: EvidenceReasoningStatus
    interaction_decision: InteractionEvidenceDecision
    claims: list[EvidenceClaim]
    supported_action: SupportedEvidenceAction | None
    missing_section_types: list[KnowledgeSectionType]
    conflict_evidence_ids: list[str]
```

Run:

```bash
uv run pytest ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py -q
```

Expected RED: 신규 모듈 import 실패.

**Step 2: strict schema와 v7 Evidence stage 체인을 구현한다**

- Evidence item은 규칙과 검색 청크를 불변 `evidence_id`로 전달한다.
- LCEL에서 입력과 모델 출력을 함께 보존한 뒤 output validator가 모든 ID를 입력 subset으로 검증한다.
- `INTERACTION_CONFIRMED`는 최소 한 개의 INTERACTION claim과 evidence ID가 있어야 한다.
- 모델 실패는 예외를 호출자에게 전달하고 호출자가 기존 결정론적 경로를 유지한다.

**Step 3: GREEN을 확인한다**

```bash
uv run pytest ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py -q
```

**Step 4: 커밋한다**

```bash
git add ai_worker/schemas/evidence_reasoning.py ai_worker/chains/interaction_evidence_reasoning_chain.py ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py
git commit -m "feat(ai): validate interaction evidence with structured reasoning"
```

## Task 5: Evidence Reasoning 조건부 런타임 연결

**Files:**

- Modify: `ai_worker/core/config.py`
- Modify: `ai_worker/services/medication_chat_core_service.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/schemas/medication_chat.py`
- Modify: `ai_worker/llm/prompts/medication_chat_prompt.py`
- Modify: `ai_worker/tests/core/test_core_package.py`
- Modify: `ai_worker/tests/services/test_medication_chat_core_service.py`
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Step 1: feature flag와 호출 조건 실패 테스트를 작성한다**

테스트가 잡아야 할 결함:

- 기본값이 활성화되어 비용·지연이 즉시 증가
- 일반 효능 질문에도 Evidence Reasoning 호출
- 상호작용 근거가 없는데 호출
- 체인 실패가 전체 답변 실패로 전파
- reasoning 결과 또는 내부 추론이 API dump에 노출
- 검증된 claims가 최종 Answer Generation payload에 전달되지 않음

Run:

```bash
uv run pytest ai_worker/tests/core/test_core_package.py ai_worker/tests/services/test_medication_chat_core_service.py ai_worker/tests/use_cases/test_answer_medication_question.py -q
```

Expected RED: 설정·의존성·호출 경로 부재로 실패.

**Step 2: 조건부 연결을 구현한다**

- `INTERACTION_EVIDENCE_REASONING_ENABLED: bool = False`를 추가한다.
- 활성화 시에만 service builder가 Evidence chain을 생성한다.
- coverage retry 후 상호작용 질문이고 규칙 또는 answer chunk가 있을 때만 호출한다.
- Trace 이름은 `medication.evidence_reasoning`으로 하고 판정, claim 수, missing section만 기록한다.
- 체인 오류·검증 실패 시 기존 `MedicationAnswerAssembler` 초안을 그대로 사용한다.
- 구조화 결과는 `MedicationChatResult`의 `exclude=True` 내부 필드로 Answer Generation까지 전달한다.

**Step 3: GREEN과 관련 회귀 테스트를 실행한다**

```bash
uv run pytest ai_worker/tests/core/test_core_package.py ai_worker/tests/services/test_medication_chat_core_service.py ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/schemas/test_medication_chat_schema.py -q
```

**Step 4: 커밋한다**

```bash
git add ai_worker/core/config.py ai_worker/services/medication_chat_core_service.py ai_worker/use_cases/answer_medication_question.py ai_worker/schemas/medication_chat.py ai_worker/llm/prompts/medication_chat_prompt.py ai_worker/tests/core/test_core_package.py ai_worker/tests/services/test_medication_chat_core_service.py ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/schemas/test_medication_chat_schema.py
git commit -m "feat(ai): gate interaction evidence reasoning at runtime"
```

## Task 6: 기존 LLM 단계의 v7 프롬프트 팩 전환

**Files:**

- Modify: `ai_worker/llm/prompts/medication_chat_prompt.py`
- Modify: `ai_worker/chains/conversation_gate_chain.py`
- Modify: `ai_worker/llm/generators/conversation_response_generator.py`
- Modify: `ai_worker/llm/generators/medication_note_summary_generator.py`
- Modify: `ai_worker/schemas/conversation_gate.py`
- Modify: `ai_worker/tests/llm/prompts/test_medication_chat_prompt.py`
- Modify: `ai_worker/tests/chains/test_conversation_gate_chain.py`
- Modify: `ai_worker/tests/llm/generators/test_conversation_response_generator.py`
- Modify: `ai_worker/tests/llm/generators/test_medication_note_summary_generator.py`

**Step 1: v7 prompt version과 단계 격리 실패 테스트를 작성한다**

테스트가 잡아야 할 결함:

- 최종 답변이 계속 v6 prompt version을 기록
- Conversation Gate에 답변 생성 규칙이 섞임
- 복약메모 요약 stage가 인과관계를 생성하도록 허용
- 최종 답변이 요청하지 않은 section 또는 프론트 고정 면책을 출력

Run:

```bash
uv run pytest ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/llm/generators/test_conversation_response_generator.py ai_worker/tests/llm/generators/test_medication_note_summary_generator.py -q
```

Expected RED: v6 version과 개별 v1 asset 사용으로 실패.

**Step 2: 각 컴포넌트가 v7의 자기 stage만 로드하도록 전환한다**

- Answer Generation은 `answer_generation` stage를 기본 사용하고 prompt version을 `medication-chat-prompt-v7`로 기록한다.
- Conversation Gate는 `conversation_gate`, 친절 응답은 `conversation_response`, 메모 요약은 `medication_note_summary`만 사용한다.
- 일정 응답은 기존 provider/assembler 경로를 유지한다.
- 기존 v1/v6 자산은 삭제하지 않고 롤백 경로로 남긴다.

**Step 3: GREEN을 확인한다**

```bash
uv run pytest ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/llm/generators/test_conversation_response_generator.py ai_worker/tests/llm/generators/test_medication_note_summary_generator.py -q
```

**Step 4: 커밋한다**

```bash
git add ai_worker/llm/prompts/medication_chat_prompt.py ai_worker/chains/conversation_gate_chain.py ai_worker/llm/generators/conversation_response_generator.py ai_worker/llm/generators/medication_note_summary_generator.py ai_worker/schemas/conversation_gate.py ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/llm/generators/test_conversation_response_generator.py ai_worker/tests/llm/generators/test_medication_note_summary_generator.py
git commit -m "feat(ai): activate medication prompt chain v7"
```

## Task 7: 전체 회귀 검증과 실험 기록

**Files:**

- Create: `docs/superpowers/experiments/2026-09-12-medication-chat-prompt-chain-v7.md`

**Step 1: 단계별 성공·실패 이유를 기록한다**

- Loader marker 검증
- Directional Query 후보 제한
- Evidence ID subset 검증
- feature flag 비활성 기본값과 fallback
- 기존 검색 tier·coverage retry 회귀
- Answer v7 형식 회귀

**Step 2: 정적 검증을 실행한다**

```bash
uv run ruff format --check ai_worker
uv run ruff check ai_worker
```

**Step 3: AI Worker 테스트를 실행한다**

```bash
uv run pytest ai_worker/tests -q
```

Expected: all tests pass.

**Step 4: 명세와 런타임 marker를 다시 검증하고 커밋한다**

```bash
git add docs/superpowers/experiments/2026-09-12-medication-chat-prompt-chain-v7.md
git commit -m "docs(ai): record prompt chain v7 verification"
```

## Definition of Done

- v7 명세·런타임 프롬프트 팩·Pydantic 모델·LCEL 체인이 코드와 테스트로 연결되어 있다.
- 최종 답변은 v7을 기본 사용하고, Directional Query는 기존 조건부 flag 아래 동작한다.
- Evidence Reasoning은 상호작용 질문에만 적용되며 기본 비활성이다.
- 모델이 생성한 entity/pair/evidence ID가 서버 입력 집합 밖이면 폐기된다.
- 기존 Exact-pair/Entity/Semantic, Small-to-Big, 최대 1회 재검색, GroundedClaimValidator가 유지된다.
- LLM 실패 시 기존 결정론적 결과를 반환한다.
- API dump와 Trace에 자유 형식 CoT가 없다.
- 관련 테스트, 전체 AI Worker 테스트, Ruff 검증이 통과한다.
