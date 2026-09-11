# Medication Note Chat Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 채팅에서 명시적으로 요청하면 최근 복약메모를 진료 건별 사실 요약으로 받고, 결과를 일반 Assistant 메시지로 저장한다.

**Architecture:** Conversation Gate는 `MEDICATION_NOTE_SUMMARY`와 기본/전체 이력 범위만 구조화해 반환한다. 전용 DB provider가 사용자 소유 `MedicationNote`를 진료 건별로 모으고, 전용 LLM generator가 메모 ID 기반의 제한된 JSON 요약을 만든다. 결정론적 assembler가 약물 목록·날짜·안내 문구를 붙여 Markdown으로 렌더링하며, 기존 ChatRepository는 새 route를 기존 `PATIENT_DB` 저장 유형으로 기록한다.

**Tech Stack:** Python 3.14, Pydantic v2, Tortoise ORM, LangChain LCEL, `ChatOpenAI.with_structured_output`, FastAPI, pytest, LangSmith.

**Spec:** `docs/superpowers/specs/2026-09-11-medication-note-chat-summary-design.md`

## Global Constraints

- 요약은 사용자가 저장한 복약메모의 사실만 압축하며, 인과관계·부작용·진단·안전성·권고를 판단하지 않는다.
- 기본 범위는 최근 6개월의 현재·종료 진료 건이며, 가장 최근 메모 기준 최대 3건이다.
- 약물 FK가 없는 메모도 증상·변화 기록으로 포함하되 내부 연결 상태를 사용자에게 표시하지 않는다.
- `전체 기록`, `이전 진료` 요청은 기간·건수 제한을 확장한다.
- 결과는 별도 요약 테이블 없이 기존 Assistant `chat_messages.content`에 저장한다.
- RAG/Qdrant, 상호작용 규칙, Aerich migration, 프론트 수정은 범위 밖이다.
- 새 LLM 출력은 strict JSON Schema로 받고 자유 형식 CoT를 출력·저장하지 않는다.
- `LANGSMITH_CAPTURE_CONTENT=false`면 원본 메모 본문을 Trace metadata에 기록하지 않는다.

## Execution Status

- Tasks 1–4와 Task 5의 자동 테스트·정적 검증은 완료했다.
- 실제 사용자 데이터로 `conversation.classify → medication_note_summary.load → medication_note_summary.generate`를 확인하는 LangSmith 수동 E2E만 서버 실행 후 진행한다.

---

## File Structure

- Create: `ai_worker/schemas/medication_note_summary.py` — provider 입력·출력, LLM payload, summary scope 계약.
- Create: `ai_worker/providers/db_medication_note_summary_provider.py` — 사용자 소유의 `MedicationNote`, `CareEpisode`, `Medication`를 진료 건 단위로 조회·정렬·제한.
- Create: `ai_worker/llm/generators/medication_note_summary_generator.py` — strict JSON LLM 호출 및 note ID 검증.
- Create: `ai_worker/llm/assemblers/medication_note_summary_assembler.py` — 합의된 Markdown 형식의 결정론적 렌더링.
- Create: `ai_worker/llm/prompts/assets/medication_note_summary_prompt_v1.md` — 사실 요약 전용 프롬프트.
- Modify: `ai_worker/schemas/conversation_gate.py` — 요약 intent 및 기본/전체 범위 enum.
- Modify: `ai_worker/llm/prompts/assets/conversation_gate_prompt_v1.md` — 명시적 복약메모 요약 요청 분류 규칙.
- Modify: `ai_worker/use_cases/answer_medication_question.py` — Gate 결과에서 전용 summary UseCase를 호출.
- Modify: `ai_worker/services/medication_chat_core_service.py` — provider·generator를 조립.
- Modify: `ai_worker/schemas/medication_chat.py` — summary route·reason code.
- Modify: `app/repositories/chat_repository.py` — summary route를 `PATIENT_DB`로 저장.
- Create/Modify tests under `ai_worker/tests/` and `tests/repositories/` — 계약, provider, generator, use case, chat persistence 회귀.

### Task 1: 진료 건별 복약메모 조회 계약과 DB Provider

**Files:**
- Create: `ai_worker/schemas/medication_note_summary.py`
- Create: `ai_worker/providers/db_medication_note_summary_provider.py`
- Create: `ai_worker/tests/providers/test_db_medication_note_summary_provider.py`

**Interfaces:**
- Produces: `MedicationNoteSummaryScope` with `RECENT_SIX_MONTHS` and `ALL_HISTORY`.
- Produces: `MedicationNoteSummaryNote`, `MedicationNoteSummaryEpisode`, `MedicationNoteSummarySelection`.
- Produces: `MedicationNoteSummaryProvider.list_episodes(user_id: int, scope: MedicationNoteSummaryScope) -> MedicationNoteSummarySelection`.
- Consumes: existing `MedicationNote`, `CareEpisode`, `Medication`, `CareEpisodeStatus` models.

- [x] **Step 1: provider의 실패 테스트를 작성한다**

```python
async def test_recent_scope_groups_notes_by_episode_and_keeps_unlinked_notes() -> None:
    provider = DbMedicationNoteSummaryProvider(today_provider=lambda: date(2026, 9, 11))

    selection = await provider.list_episodes(user_id=1, scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS)

    assert [episode.care_episode_id for episode in selection.episodes] == [newer_episode.id, older_episode.id]
    assert [note.body for note in selection.episodes[0].notes] == ["두통", "속쓰림"]
    assert selection.episodes[0].notes[1].medication_name is None


async def test_recent_scope_returns_only_three_latest_episodes_and_marks_more() -> None:
    provider = DbMedicationNoteSummaryProvider(today_provider=lambda: date(2026, 9, 11))

    selection = await provider.list_episodes(user_id=1, scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS)

    assert len(selection.episodes) == 3
    assert selection.has_more_episodes is True


async def test_all_history_scope_includes_closed_episode_before_six_month_cutoff() -> None:
    provider = DbMedicationNoteSummaryProvider(today_provider=lambda: date(2026, 9, 11))

    selection = await provider.list_episodes(user_id=1, scope=MedicationNoteSummaryScope.ALL_HISTORY)

    assert historical_episode.id in [episode.care_episode_id for episode in selection.episodes]
```

- [x] **Step 2: 테스트가 import 오류로 실패하는지 확인한다**

Run: `uv run --group ai pytest ai_worker/tests/providers/test_db_medication_note_summary_provider.py -q`

Expected: `ModuleNotFoundError` for `medication_note_summary`.

- [x] **Step 3: 최소 스키마와 provider를 구현한다**

```python
class MedicationNoteSummaryScope(StrEnum):
    RECENT_SIX_MONTHS = "RECENT_SIX_MONTHS"
    ALL_HISTORY = "ALL_HISTORY"


class MedicationNoteSummaryProvider(Protocol):
    async def list_episodes(
        self,
        *,
        user_id: int,
        scope: MedicationNoteSummaryScope,
    ) -> MedicationNoteSummarySelection: ...
```

`DbMedicationNoteSummaryProvider`는 `dosed_at >= today - relativedelta(months=6)`을 기본 필터로 사용한다. `ALL_HISTORY`에는 날짜 필터를 적용하지 않는다. `MedicationNote`가 있는 episode만 사용자 소유 조건으로 조회하고 `medications`를 prefetch 한다. 각 episode의 최대 `dosed_at`으로 내림차순 정렬한 뒤 기본 범위에서 네 번째 episode까지 읽어 `has_more_episodes`를 계산하고 처음 세 건만 반환한다. episode 안의 note는 `dosed_at`, `id` 오름차순으로 반환한다.

- [x] **Step 4: provider 테스트를 통과시킨다**

Run: `uv run --group ai pytest ai_worker/tests/providers/test_db_medication_note_summary_provider.py -q`

Expected: PASS.

- [x] **Step 5: 커밋한다**

```bash
git add ai_worker/schemas/medication_note_summary.py ai_worker/providers/db_medication_note_summary_provider.py ai_worker/tests/providers/test_db_medication_note_summary_provider.py
git commit -m "feat(ai): load medication notes by care episode"
```

### Task 2: 사실 요약 LLM 계약과 Markdown Assembler

**Files:**
- Create: `ai_worker/llm/prompts/assets/medication_note_summary_prompt_v1.md`
- Create: `ai_worker/llm/generators/medication_note_summary_generator.py`
- Create: `ai_worker/llm/assemblers/medication_note_summary_assembler.py`
- Create: `ai_worker/tests/llm/generators/test_medication_note_summary_generator.py`
- Create: `ai_worker/tests/llm/assemblers/test_medication_note_summary_assembler.py`

**Interfaces:**
- Produces: `MedicationNoteSummaryPayload` with one `summary` per input `note_id` and one `one_line_summary` per input `care_episode_id`.
- Produces: `MedicationNoteSummaryGenerator.generate(selection: MedicationNoteSummarySelection) -> MedicationNoteSummaryPayload`.
- Produces: `MedicationNoteSummaryAssembler.assemble(selection, payload) -> str`.
- Consumes: Task 1 selection models and ChatOpenAI strict JSON schema client.

- [x] **Step 1: LLM payload 검증과 출력 형식의 실패 테스트를 작성한다**

```python
async def test_generator_rejects_unknown_note_id_from_model() -> None:
    generator = build_medication_note_summary_generator(client=FakeClient(note_ids=[999]))

    with pytest.raises(MedicationNoteSummaryGenerationError, match="note_id"):
        await generator.generate(selection)


async def test_generator_rejects_causal_claims() -> None:
    generator = build_medication_note_summary_generator(client=FakeClient(summary="약물 부작용으로 두통 발생"))

    with pytest.raises(MedicationNoteSummaryGenerationError, match="인과"):
        await generator.generate(selection)


def test_assembler_renders_episode_blocks_and_recent_three_notice() -> None:
    answer = MedicationNoteSummaryAssembler().assemble(selection_with_more, payload)

    assert "💉 **과거 복약 정보 · A병원 진료**" in answer
    assert "📝 **복약메모 요약**" in answer
    assert "⭐️ **한줄 요약**" in answer
    assert "최근 3건의 진료 기록만 정리했습니다" in answer
    assert "약물 연결 없음" not in answer
```

- [x] **Step 2: 테스트가 구현 부재로 실패하는지 확인한다**

Run: `uv run --group ai pytest ai_worker/tests/llm/generators/test_medication_note_summary_generator.py ai_worker/tests/llm/assemblers/test_medication_note_summary_assembler.py -q`

Expected: `ModuleNotFoundError` for the generator and assembler.

- [x] **Step 3: strict JSON generator를 구현한다**

```python
class MedicationNoteSummaryItem(BaseModel):
    note_id: int = Field(gt=0)
    summary: str = Field(min_length=1, max_length=180)


class MedicationNoteEpisodeSummary(BaseModel):
    care_episode_id: int = Field(gt=0)
    note_summaries: list[MedicationNoteSummaryItem]
    one_line_summary: str = Field(min_length=1, max_length=240)
```

`ChatOpenAI(...).with_structured_output(MedicationNoteSummaryPayload, method="json_schema", strict=True)`를 사용한다. 프롬프트에는 입력 episode·note ID와 원문만 제공하고, `부작용`, `원인`, `약물 때문에`, `안전`, `위험`, `권장`을 인과·의료 판단으로 사용하지 말도록 지시한다. generator는 episode ID와 note ID 집합이 입력과 정확히 같은지 확인하고, 출력 문구에 금지된 판단 표현이 있으면 `MedicationNoteSummaryGenerationError`로 실패시킨다.

`MedicationNoteSummaryAssembler`는 날짜·약물 목록·구분선·면책 문구를 결정론적으로 붙인다. LLM은 제목, 날짜, 약물 목록, 추가 안내 문구를 만들지 않는다.

- [x] **Step 4: generator·assembler 테스트를 통과시킨다**

Run: `uv run --group ai pytest ai_worker/tests/llm/generators/test_medication_note_summary_generator.py ai_worker/tests/llm/assemblers/test_medication_note_summary_assembler.py -q`

Expected: PASS.

- [x] **Step 5: 커밋한다**

```bash
git add ai_worker/llm/prompts/assets/medication_note_summary_prompt_v1.md ai_worker/llm/generators/medication_note_summary_generator.py ai_worker/llm/assemblers/medication_note_summary_assembler.py ai_worker/tests/llm/generators/test_medication_note_summary_generator.py ai_worker/tests/llm/assemblers/test_medication_note_summary_assembler.py
git commit -m "feat(ai): generate factual medication note summaries"
```

### Task 3: Conversation Gate의 명시적 복약메모 요약 분류

**Files:**
- Modify: `ai_worker/schemas/conversation_gate.py`
- Modify: `ai_worker/llm/prompts/assets/conversation_gate_prompt_v1.md`
- Modify: `ai_worker/chains/conversation_gate_chain.py`
- Modify: `ai_worker/tests/chains/test_conversation_gate_chain.py`
- Modify: `ai_worker/tests/domain/test_conversation_safety_policy.py`

**Interfaces:**
- Produces: `ConversationIntent.MEDICATION_NOTE_SUMMARY`.
- Produces: `ConversationClassification.note_summary_scope: MedicationNoteSummaryScope | None`.
- Consumes: `MedicationNoteSummaryScope` from Task 1.

- [x] **Step 1: Gate 분류 실패 테스트를 작성한다**

```python
def test_note_summary_request_is_allowed_and_uses_recent_scope() -> None:
    classification = ConversationClassification(
        intent="MEDICATION_NOTE_SUMMARY",
        safety_signal="NONE",
        confidence="HIGH",
        note_summary_scope="RECENT_SIX_MONTHS",
    )

    assert ConversationSafetyPolicy().decide(classification).disposition == "ALLOW"


def test_full_history_note_summary_request_uses_all_history_scope() -> None:
    prompt = render_gate_prompt("전체 복약메모를 진료용으로 정리해줘")

    assert "MEDICATION_NOTE_SUMMARY" in prompt
    assert "ALL_HISTORY" in prompt
```

- [x] **Step 2: 테스트가 새 enum/field 부재로 실패하는지 확인한다**

Run: `uv run --group ai pytest ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/domain/test_conversation_safety_policy.py -q`

Expected: missing `MEDICATION_NOTE_SUMMARY` or `note_summary_scope` failure.

- [x] **Step 3: Gate schema와 prompt를 확장한다**

`ConversationIntent`에 `MEDICATION_NOTE_SUMMARY`를 추가한다. `ConversationClassification.note_summary_scope`는 기본 `None`이며, intent가 `MEDICATION_NOTE_SUMMARY`일 때만 `RECENT_SIX_MONTHS` 또는 `ALL_HISTORY`를 허용하는 model validator를 추가한다.

Gate prompt에 아래 구분을 명시한다.

```text
- "복약메모 정리해줘", "진료용 메모 요약해줘"는 MEDICATION_NOTE_SUMMARY + RECENT_SIX_MONTHS.
- "전체 복약메모", "이전 진료 기록까지"는 MEDICATION_NOTE_SUMMARY + ALL_HISTORY.
- 약 효능, 용법, 상호작용을 묻는 질문은 MEDICATION_NOTE_SUMMARY가 아니다.
```

기존 `ConversationSafetyPolicy`의 `ALLOW` 기본 동작은 유지한다. 위해·응급 신호가 있으면 기존 BLOCK/URGENT 우선순위가 먼저 적용되는지 회귀 테스트를 추가한다.

- [x] **Step 4: Gate 계약 테스트를 통과시킨다**

Run: `uv run --group ai pytest ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/domain/test_conversation_safety_policy.py -q`

Expected: PASS.

- [x] **Step 5: 커밋한다**

```bash
git add ai_worker/schemas/conversation_gate.py ai_worker/llm/prompts/assets/conversation_gate_prompt_v1.md ai_worker/chains/conversation_gate_chain.py ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/domain/test_conversation_safety_policy.py
git commit -m "feat(ai): classify medication note summary requests"
```

### Task 4: Chat UseCase와 저장 route 통합

**Files:**
- Create: `ai_worker/use_cases/medication_note_summary.py`
- Create: `ai_worker/tests/use_cases/test_medication_note_summary.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/services/medication_chat_core_service.py`
- Modify: `ai_worker/schemas/medication_chat.py`
- Modify: `app/repositories/chat_repository.py`
- Modify: `tests/repositories/test_chat_repository.py`

**Interfaces:**
- Produces: `MedicationNoteSummaryUseCase.execute(request: MedicationChatRequest, scope: MedicationNoteSummaryScope) -> MedicationChatResult`.
- Produces: `MedicationChatRoute.MEDICATION_NOTE_SUMMARY` and `MedicationChatReasonCode.MEDICATION_NOTE_SUMMARY_REQUESTED` / `MEDICATION_NOTE_SUMMARY_UNAVAILABLE`.
- Consumes: Tasks 1–3 provider, generator, assembler, Gate classification.

- [x] **Step 1: UseCase·저장 route의 실패 테스트를 작성한다**

```python
async def test_summary_intent_returns_assistant_result_without_rag_lookup() -> None:
    result = await use_case.execute(request_for("복약메모 정리해줘"))

    assert result.route == MedicationChatRoute.MEDICATION_NOTE_SUMMARY
    assert result.safety_status == SafetyStatus.SAFE
    assert "💉 **과거 복약 정보" in result.answer
    knowledge_retriever.assert_not_called()


async def test_summary_with_no_notes_does_not_call_llm() -> None:
    result = await use_case.execute(request_for("진료용 메모 정리해줘"))

    assert result.answer == "📝 최근 6개월 동안 기록된 복약메모가 없습니다."
    summary_generator.assert_not_called()


def test_summary_route_is_persisted_as_patient_db() -> None:
    assert ChatRepository._chat_route(summary_result) is ChatRouteType.PATIENT_DB
```

- [x] **Step 2: 테스트가 route·UseCase 부재로 실패하는지 확인한다**

Run: `uv run --group ai pytest ai_worker/tests/use_cases/test_medication_note_summary.py tests/repositories/test_chat_repository.py -q`

Expected: missing summary UseCase, route, or reason code failure.

- [x] **Step 3: 전용 UseCase를 조립하고 Gate 분기에 연결한다**

`MedicationNoteSummaryUseCase`는 provider 조회를 LangSmith `medication_note_summary.load` tool span으로, LLM 요약을 `medication_note_summary.generate` span으로 남긴다. content capture가 꺼진 경우 span에는 episode·note 본문 대신 건수·scope·duration만 기록한다.

`AnswerMedicationQuestionUseCase._conversation_classification_result()`는 `MEDICATION_NOTE_SUMMARY`를 먼저 처리한다. 성공 결과는 RAG·상호작용 규칙·GroundedClaimValidator를 거치지 않는다. provider 또는 generator 오류는 `MEDICATION_NOTE_SUMMARY_UNAVAILABLE` reason code와 재시도 안내를 반환한다.

`MedicationChatCoreService`는 `DbMedicationNoteSummaryProvider`와 새 generator를 조립한다. `ChatRepository._chat_route()`는 `MEDICATION_NOTE_SUMMARY`를 기존 `ChatRouteType.PATIENT_DB`로 매핑하므로 DB enum migration은 필요 없다.

- [x] **Step 4: UseCase·repository 테스트를 통과시킨다**

Run: `uv run --group ai pytest ai_worker/tests/use_cases/test_medication_note_summary.py ai_worker/tests/use_cases/test_answer_medication_question.py tests/repositories/test_chat_repository.py -q`

Expected: PASS.

- [x] **Step 5: 커밋한다**

```bash
git add ai_worker/use_cases/medication_note_summary.py ai_worker/tests/use_cases/test_medication_note_summary.py ai_worker/use_cases/answer_medication_question.py ai_worker/services/medication_chat_core_service.py ai_worker/schemas/medication_chat.py app/repositories/chat_repository.py tests/repositories/test_chat_repository.py
git commit -m "feat(chat): summarize medication notes in conversations"
```

### Task 5: 전체 회귀·Trace·출력 계약 검증

**Files:**
- Create: `ai_worker/tests/evaluation/test_medication_note_summary_contract.py`
- Modify: `docs/superpowers/specs/2026-09-11-medication-note-chat-summary-design.md` only if verified behavior differs from the approved contract.

**Interfaces:**
- Consumes: Tasks 1–4 implementation and the existing chat regression suite.
- Produces: recent/default, full-history, three-episode cap, no-note, and medication-question regression evidence.

- [x] **Step 1: end-to-end 계약 테스트를 작성한다**

```python
async def test_default_summary_has_three_episode_cap_and_exact_notice() -> None:
    result = await execute_chat("복약메모 정리해줘", seeded_user_with_four_recent_episodes)

    assert result.answer.count("💉 **과거 복약 정보") == 3
    assert "📌 최근 3건의 진료 기록만 정리했습니다. 이전 진료 기록도 필요하면 말씀해 주세요." in result.answer


async def test_full_history_summary_does_not_change_medication_rag_question() -> None:
    await execute_chat("전체 복약메모를 정리해줘", seeded_user)
    medication_result = await execute_chat("타이레놀 효능과 주의사항을 알려줘", seeded_user)

    assert medication_result.route == MedicationChatRoute.MEDICATION_GUIDE
```

- [x] **Step 2: 새 계약 테스트가 구현 결함을 드러내는지 확인한다**

Run: `uv run --group ai pytest ai_worker/tests/evaluation/test_medication_note_summary_contract.py -q`

Expected: PASS after Tasks 1–4; if it fails, correct implementation rather than relaxing the approved output contract.

- [x] **Step 3: 전체 관련 테스트와 정적 검사를 실행한다**

Run: `uv run --group ai pytest ai_worker/tests/providers/test_db_medication_note_summary_provider.py ai_worker/tests/llm/generators/test_medication_note_summary_generator.py ai_worker/tests/llm/assemblers/test_medication_note_summary_assembler.py ai_worker/tests/chains/test_conversation_gate_chain.py ai_worker/tests/use_cases/test_medication_note_summary.py ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/evaluation/test_medication_note_summary_contract.py tests/repositories/test_chat_repository.py -q`

Expected: PASS.

Run: `uv run --group ai ruff check ai_worker app tests`

Expected: PASS.

- [ ] **Step 4: LangSmith 실측을 확인한다**

`복약메모 정리해줘`와 `전체 복약메모를 진료용으로 정리해줘`를 실행해 다음 span만 확인한다.

```text
conversation.classify
medication_note_summary.load
medication_note_summary.generate
```

`타이레놀 효능과 주의사항을 알려줘`에는 `medication_note_summary.*` span이 없어야 한다. `LANGSMITH_CAPTURE_CONTENT=false`에서 메모 원문이 metadata에 없는지도 확인한다.

- [x] **Step 5: 커밋한다**

```bash
git add ai_worker/tests/evaluation/test_medication_note_summary_contract.py
git commit -m "test(ai): verify medication note summary flow"
```

## Plan Self-Review

- Spec coverage: 최근 6개월 기본 범위, 현재·종료 episode, 3건 제한, 전체 이력 확장, 미연결 메모 포함, 사실 요약, 진료 건별 Markdown, ChatMessage 저장, RAG 비사용, 오류 처리, Trace 검증이 Tasks 1–5에 각각 대응한다.
- Placeholder scan: `TODO`, `TBD`, 미정 함수명, 추상적 오류 처리 표현 없이 provider·generator·route·테스트 명령을 명시했다.
- Type consistency: `MedicationNoteSummaryScope`는 Task 1에서 정의해 Task 3 Gate와 Task 4 UseCase가 사용한다. `MedicationNoteSummarySelection`은 Task 1 provider 출력, Task 2 generator 입력, Task 4 UseCase 입력으로 동일하다.
