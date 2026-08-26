# #111 Chat Session Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the active chatbot conversation across in-app tab changes and provide a mock-backed, newest-first conversation list with new-chat and multi-delete interactions.

**Architecture:** Keep `/chat` as the only route and store only `activeSessionId` in a provider mounted above `Routes`. Put session/message persistence behind `entities/chat`; its temporary mock repository uses namespaced `localStorage` to emulate a database across reloads, while page components consume typed functions and remain independent of the eventual HTTP contract.

**Tech Stack:** React 19, TypeScript, React Router 7, Tailwind CSS tokens, Radix Dialog, Playwright, Vite mock environment

**Spec:** `docs/superpowers/specs/2026-08-26-chat-session-frontend-design.md`

## Global Constraints

- Modify `frontend/` only after this plan document; do not modify ERD, backend models, routers, services, migrations, or OpenAPI.
- Do not invent real session-list/history/delete endpoint paths or DTOs in this issue.
- Keep the existing `/chat` route and existing `sendChat()` real API branch intact.
- Use the mock repository only as a frontend verification substitute; the page must access it through `entities/chat` functions.
- Store only the active session ID in React context; do not keep the message array in global context.
- Derive the list title from the first user message and the subtitle from the last message.
- New chat sessions are created only after the first successful question.
- Provide explicit `선택` controls for mouse and touch; do not make long press the only path.
- Use existing design tokens and shared controls; retain minimum 44px touch targets.
- Preserve `ChatStartGuide`, FAQ immediate-send behavior, source display, and inline history-load failure behavior.

---

## File Structure

- Create `frontend/src/app/ChatSessionContext.tsx`: runtime-only active session selection.
- Modify `frontend/src/app/router.tsx`: mount `ChatSessionProvider` above `Routes`; keep `/chat` unchanged.
- Modify `frontend/src/entities/chat/types.ts`: session summary and session repository result types.
- Modify `frontend/src/entities/chat/api.mock.ts`: namespaced mock session/message persistence.
- Modify `frontend/src/entities/chat/api.ts`: typed session list/history/delete functions backed by the mock repository for this issue.
- Modify `frontend/src/entities/chat/index.ts`: export new functions and types.
- Create `frontend/src/pages/chat/ChatSessionList.tsx`: newest-first list and selection mode.
- Create `frontend/src/pages/chat/ChatDeleteDialog.tsx`: destructive multi-delete confirmation.
- Modify `frontend/src/pages/chat/ChatPage.tsx`: entry-state controller and existing room integration.
- Modify `frontend/tests/e2e/chat-start-guide.spec.ts`: retain empty/history regressions under the new entry logic.
- Create `frontend/tests/e2e/chat-session-flow.spec.ts`: resume, reload list, new chat, selection, and deletion behaviors.

---

### Task 1: Preserve the Active Conversation Across In-App Tab Changes

**Files:**
- Create: `frontend/src/app/ChatSessionContext.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/entities/chat/types.ts`
- Modify: `frontend/src/entities/chat/api.mock.ts`
- Modify: `frontend/src/entities/chat/api.ts`
- Modify: `frontend/src/entities/chat/index.ts`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Create: `frontend/tests/e2e/chat-session-flow.spec.ts`

**Interfaces:**
- Produces: `useChatSession(): { activeSessionId: number | null; selectSession(id: number): void; startNewSession(): void }`
- Produces: `getChatMessages(sessionId: number): Promise<ChatMessage[]>`
- Produces: mock persistence as an internal side effect of `mockSendChat(payload)`.
- Consumes: existing `sendChat(payload: SendChatPayload): Promise<SendChatResult>`.

- [ ] **Step 1: Write the failing tab-resume test**

Create `frontend/tests/e2e/chat-session-flow.spec.ts` with a test that sends a FAQ, waits for the mock answer, changes to Home through the bottom tab, returns through the Chat tab, and expects both messages to remain:

```ts
import { expect, test } from 'playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/dev/chat');
  await page.evaluate(() => localStorage.removeItem('poke.mock-chat-sessions'));
  await page.reload();
});

test('다른 하단 탭에 다녀오면 활성 채팅방과 메시지를 다시 불러온다', async ({ page }) => {
  const question = '지금 먹는 약을 같이 먹어도 되나요?';
  await page.getByRole('button', { name: question }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.getByRole('button', { name: '홈' }).click();
  await page.getByRole('button', { name: '챗봇' }).click();

  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
});
```

- [ ] **Step 2: Run the test and verify the current reset**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts --grep "다른 하단 탭"
```

Expected: FAIL because `ChatPage` remounts with empty `messages` and `conversationId`.

- [ ] **Step 3: Add the runtime-only active session context**

Create `ChatSessionContext.tsx` with this public shape:

```tsx
interface ChatSessionValue {
  activeSessionId: number | null;
  selectSession: (sessionId: number) => void;
  startNewSession: () => void;
}

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const value = useMemo(
    () => ({
      activeSessionId,
      selectSession: setActiveSessionId,
      startNewSession: () => setActiveSessionId(null),
    }),
    [activeSessionId],
  );
  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>;
}
```

Wrap `Routes` in `ChatSessionProvider` inside the existing `BrowserRouter`. Do not add a new route.

- [ ] **Step 4: Add mock session persistence and history retrieval**

Extend `types.ts` with:

```ts
export interface ChatSessionSummary {
  sessionId: number;
  title: string;
  lastMessagePreview: string;
  lastMessageAt: string;
}
```

In `api.mock.ts`, store this private shape under `poke.mock-chat-sessions`:

```ts
interface MockStoredSession {
  sessionId: number;
  createdAt: string;
  lastMessageAt: string;
  messages: ChatMessage[];
}

interface MockChatStore {
  nextSessionId: number;
  nextMessageId: number;
  sessions: MockStoredSession[];
}
```

Update `mockSendChat()` so a null `conversationId` allocates `nextSessionId`, appends the user and assistant messages only after producing a successful mock response, updates `lastMessageAt`, and writes the store. Add:

```ts
export function mockGetChatMessages(sessionId: number): ChatMessage[] {
  const session = readStore().sessions.find((item) => item.sessionId === sessionId);
  if (!session) throw new Error('대화를 찾지 못했어요.');
  return structuredClone(session.messages);
}
```

In `api.ts`, expose `getChatMessages()` through the entity boundary. For #111, call the mock implementation after `mockDelay()` and leave a comment that the real HTTP mapping waits for the backend contract; do not add a guessed URL.

- [ ] **Step 5: Load the active session when ChatPage remounts**

In `ChatPage`, read `activeSessionId` from `useChatSession()`. When no explicit `historyLoader` is supplied and the ID is non-null, call `getChatMessages(activeSessionId)`, populate `messages`, and set the local `conversationId`. After a successful first send, call `selectSession(result.conversationId)` as well as setting the local ID.

Keep the explicit `historyLoader` dev-gallery behavior unchanged so existing `/dev/chat-history` and `/dev/chat-history-error` tests remain deterministic.

- [ ] **Step 6: Run the focused and existing chat tests**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts --grep "다른 하단 탭"
pnpm exec playwright test tests/e2e/chat-start-guide.spec.ts
```

Expected: both commands PASS.

- [ ] **Step 7: Commit the active-session slice**

```bash
git add frontend/src/app/ChatSessionContext.tsx frontend/src/app/router.tsx frontend/src/entities/chat frontend/src/pages/chat/ChatPage.tsx frontend/tests/e2e/chat-session-flow.spec.ts
git commit -m "[feature/111][신동훈]챗봇 활성 세션 유지"
```

---

### Task 2: Add Cold-Start Session List and New Chat

**Files:**
- Modify: `frontend/src/entities/chat/api.mock.ts`
- Modify: `frontend/src/entities/chat/api.ts`
- Modify: `frontend/src/entities/chat/index.ts`
- Create: `frontend/src/pages/chat/ChatSessionList.tsx`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Modify: `frontend/tests/e2e/chat-session-flow.spec.ts`

**Interfaces:**
- Consumes: `ChatSessionSummary`, `getChatMessages()`, and `useChatSession()` from Task 1.
- Produces: `listChatSessions(): Promise<ChatSessionSummary[]>`.
- Produces: `ChatSessionList` callbacks `onOpen(sessionId)` and `onNewChat()`.

- [ ] **Step 1: Write failing reload-list and new-chat tests**

Append tests that create one conversation, reload `/dev/chat`, assert a list row with the first question as title and assistant response as preview, open it, and start a blank chat using the `새 채팅` button:

```ts
test('새로고침하면 최신 대화 목록을 보여주고 선택한 세션을 연다', async ({ page }) => {
  const question = '영양제와 같이 먹어도 괜찮나요?';
  await page.getByRole('button', { name: question }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
  const row = page.getByRole('button', { name: new RegExp(question) });
  await expect(row).toContainText(question);
  await expect(row).toContainText('리바록사반을 복용하는 동안');

  await row.click();
  await expect(page.getByText(question, { exact: true })).toBeVisible();
});

test('새 채팅 버튼은 빈 세션을 저장하지 않고 시작 가이드를 연다', async ({ page }) => {
  await page.getByRole('button', { name: '이 약은 왜 먹는 건가요?' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  await page.reload();

  await page.getByRole('button', { name: '새 채팅' }).click();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
  await expect(page.getByRole('button', { name: /이 약은 왜 먹는 건가요/ })).toHaveCount(1);
});
```

- [ ] **Step 2: Run the tests and verify list controls are absent**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts --grep "새로고침|새 채팅"
```

Expected: FAIL because cold entry still opens an empty room and there is no list or `새 채팅` button.

- [ ] **Step 3: Implement newest-first summaries behind entities/chat**

Add `mockListChatSessions()` that maps stored sessions to summaries and sorts descending:

```ts
return readStore().sessions
  .map((session) => ({
    sessionId: session.sessionId,
    title: session.messages.find((message) => message.role === 'user')?.text ?? '새 대화',
    lastMessagePreview: session.messages.at(-1)?.text ?? '',
    lastMessageAt: session.lastMessageAt,
  }))
  .sort((left, right) => right.lastMessageAt.localeCompare(left.lastMessageAt));
```

Expose `listChatSessions()` in `api.ts` and `index.ts` using the same mock-only boundary rule as Task 1.

- [ ] **Step 4: Create the session list UI**

Create `ChatSessionList.tsx` with:

```tsx
interface ChatSessionListProps {
  sessions: ChatSessionSummary[];
  onOpen: (sessionId: number) => void;
  onNewChat: () => void;
}
```

Render `Header` with `+` as a minimum-touch icon button with `aria-label="새 채팅"`, a `최근 대화` heading, and full-row buttons. Use `truncate`, token colors, token spacing, and a Korean `Intl.DateTimeFormat` for the timestamp; do not hardcode hex colors or arbitrary pixel values.

- [ ] **Step 5: Make ChatPage an entry-state controller**

Use an explicit view state:

```ts
type ChatView = 'loading' | 'list' | 'room';
```

On initial mount without a legacy `historyLoader`:

1. If `activeSessionId` is non-null, load that room.
2. Otherwise call `listChatSessions()`.
3. If the result is empty, show a new room.
4. If the result has entries, show the list.

`onOpen` selects the session, loads its messages, and displays the room. `onNewChat` clears the active ID, messages, local conversation ID, draft, and errors before showing the room. The room header back action displays the list when stored sessions exist; it must not use `navigate(-1)` for this internal transition.

- [ ] **Step 6: Run list, new-chat, and guide regressions**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts --grep "새로고침|새 채팅"
pnpm exec playwright test tests/e2e/chat-start-guide.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Commit the list slice**

```bash
git add frontend/src/entities/chat frontend/src/pages/chat/ChatSessionList.tsx frontend/src/pages/chat/ChatPage.tsx frontend/tests/e2e/chat-session-flow.spec.ts
git commit -m "[feature/111][신동훈]챗봇 대화 목록과 새 채팅 추가"
```

---

### Task 3: Add Mouse-and-Touch Multi-Selection and Deletion

**Files:**
- Modify: `frontend/src/entities/chat/api.mock.ts`
- Modify: `frontend/src/entities/chat/api.ts`
- Modify: `frontend/src/entities/chat/index.ts`
- Modify: `frontend/src/pages/chat/ChatSessionList.tsx`
- Create: `frontend/src/pages/chat/ChatDeleteDialog.tsx`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Modify: `frontend/tests/e2e/chat-session-flow.spec.ts`

**Interfaces:**
- Consumes: `ChatSessionSummary[]` and list callbacks from Task 2.
- Produces: `deleteChatSessions(sessionIds: number[]): Promise<void>`.
- Produces: explicit selection mode with `selectedSessionIds: Set<number>`.

- [ ] **Step 1: Write failing selection, cancel, and confirm tests**

Import `Page` and add this helper at the top of `chat-session-flow.spec.ts`; it sends a typed question and waits for the persisted mock answer:

```ts
import type { Page } from 'playwright/test';

async function createConversation(page: Page, question: string) {
  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}
```

Then assert the header `선택` button exposes checkboxes, mouse clicks select two rows, cancellation preserves both, and confirmation removes both:

```ts
test('선택 모드에서 마우스로 여러 대화를 고르고 삭제할 수 있다', async ({ page }) => {
  await createConversation(page, '첫 번째 상담 질문');
  await page.reload();
  await page.getByRole('button', { name: '새 채팅' }).click();
  await createConversation(page, '두 번째 상담 질문');
  await page.reload();

  await page.getByRole('button', { name: '대화 선택' }).click();
  await page.getByRole('checkbox', { name: /첫 번째 상담 질문/ }).check();
  await page.getByRole('checkbox', { name: /두 번째 상담 질문/ }).check();
  await expect(page.getByRole('button', { name: '2개 삭제' })).toBeEnabled();

  await page.getByRole('button', { name: '2개 삭제' }).click();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByText('첫 번째 상담 질문', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '2개 삭제' }).click();
  await page.getByRole('button', { name: '삭제' }).click();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
});
```

- [ ] **Step 2: Run the test and verify selection controls are absent**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts --grep "여러 대화"
```

Expected: FAIL because no selection or deletion controls exist.

- [ ] **Step 3: Add mock multi-delete**

Implement `mockDeleteChatSessions(sessionIds)` by filtering those IDs from the namespaced store and writing it back. Expose `deleteChatSessions()` through `api.ts` and `index.ts`; reject an empty ID array before touching storage.

```ts
export async function deleteChatSessions(sessionIds: number[]): Promise<void> {
  if (sessionIds.length === 0) return;
  await mockDelay();
  mockDeleteChatSessions(sessionIds);
}
```

- [ ] **Step 4: Add explicit selection mode**

Extend `ChatSessionList` with:

```tsx
interface ChatSessionListProps {
  sessions: ChatSessionSummary[];
  selectionMode: boolean;
  selectedSessionIds: ReadonlySet<number>;
  onToggleSelectionMode: () => void;
  onToggleSession: (sessionId: number) => void;
  onDeleteSelected: () => void;
  onOpen: (sessionId: number) => void;
  onNewChat: () => void;
}
```

Normal mode renders `+` and `선택`. Selection mode renders `취소`, row checkboxes, and a bottom fixed `N개 삭제` button disabled at zero. The checkbox label includes the title so mouse and screen-reader users can identify the row. Row click opens a chat only in normal mode and toggles selection only in selection mode.

- [ ] **Step 5: Add destructive confirmation and failure handling**

Create `ChatDeleteDialog.tsx` using the existing Radix `Dialog` primitives and shared `Button`:

```tsx
interface ChatDeleteDialogProps {
  open: boolean;
  count: number;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}
```

Use title `선택한 대화를 삭제할까요?`, description `삭제한 대화는 목록에서 다시 볼 수 없어요.`, secondary `취소`, and primary `삭제`. In `ChatPage`, call `deleteChatSessions([...selectedSessionIds])`; on success remove the rows, clear selection mode, and clear the active ID if it was selected. On failure retain selection and show `ErrorDialog` with `대화를 삭제하지 못했어요` and retry.

- [ ] **Step 6: Run the deletion test and the complete chat suite**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-session-flow.spec.ts
pnpm exec playwright test tests/e2e/chat-start-guide.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Commit the deletion slice**

```bash
git add frontend/src/entities/chat frontend/src/pages/chat frontend/tests/e2e/chat-session-flow.spec.ts
git commit -m "[feature/111][신동훈]챗봇 대화 다중 삭제 추가"
```

---

### Task 4: Verify Error States, Accessibility, and 375px Layout

**Files:**
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Modify: `frontend/tests/e2e/chat-start-guide.spec.ts`
- Modify: `frontend/tests/e2e/chat-session-flow.spec.ts`

**Interfaces:**
- Consumes: all session functions and components from Tasks 1-3.
- Produces: stable dev-gallery failure states and regression coverage.

- [ ] **Step 1: Add failing load-error and layout assertions**

Retain `/dev/chat-history-error` for legacy history failure. Add this optional dependency to `ChatPageProps`, defaulting to the entity function:

```ts
type ChatSessionListLoader = () => Promise<ChatSessionSummary[]>;

interface ChatPageProps {
  historyLoader?: ChatHistoryLoader;
  chatSender?: ChatSender;
  sessionListLoader?: ChatSessionListLoader;
}
```

In `router.tsx`, define and register one deterministic failure route:

```tsx
const failChatSessionList = async (): Promise<ChatSessionSummary[]> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};

<Route
  path="/dev/chat-session-list-error"
  element={<ChatPage sessionListLoader={failChatSessionList} />}
/>
```

Add a test that opens this route and asserts `대화 목록을 불러오지 못했어요.` is an inline card, `다시 시도` is available, and no dialog is rendered. Add a separate 375px overflow assertion:

```ts
await page.setViewportSize({ width: 375, height: 812 });
await page.goto('/dev/chat');
expect(
  await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
).toBe(true);
```

Also assert `새 채팅`, `대화 선택`, row checkboxes, and delete controls have accessible names.

- [ ] **Step 2: Run the focused tests and verify the new assertions fail before corrections**

Run:

```bash
cd frontend
pnpm exec playwright test tests/e2e/chat-start-guide.spec.ts tests/e2e/chat-session-flow.spec.ts
```

Expected: any missing inline error or overflow assertion FAILS before final adjustment.

- [ ] **Step 3: Make the minimal accessibility and layout corrections**

Use existing token classes such as `px-page-x`, `min-h-touch`, `bg-card`, `border-border`, `text-foreground`, and `text-muted-foreground`. Add `min-w-0`, `truncate`, and bottom padding equal to the fixed selection action area where required. Do not introduce hex colors or untracked pixel literals.

- [ ] **Step 4: Run full verification**

Run:

```bash
cd frontend
pnpm typecheck
pnpm build
pnpm exec playwright test tests/e2e/chat-start-guide.spec.ts tests/e2e/chat-session-flow.spec.ts
```

Expected: all commands exit 0.

- [ ] **Step 5: Confirm the change boundary**

Run:

```bash
git status --short
git diff --name-only main...HEAD
git diff --check main...HEAD
```

Expected: implementation changes are under `frontend/`; the approved design and plan documents are under `docs/superpowers/`; pre-existing `README.md`, API document, and `docs/ui-reference/` changes remain uncommitted and untouched.

- [ ] **Step 6: Commit final verification adjustments**

```bash
git add frontend/src/app/router.tsx frontend/src/pages/chat frontend/tests/e2e/chat-start-guide.spec.ts frontend/tests/e2e/chat-session-flow.spec.ts
git commit -m "[feature/111][신동훈]챗봇 세션 화면 검증 보강"
```
