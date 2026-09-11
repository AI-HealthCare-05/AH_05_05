# Conversational Safety Routing — Evaluation Results

**Date:** 2026-09-11  
**Branch:** `feature/405`  
**Default flag:** `CONVERSATION_GATE_ENABLED=false` (unchanged)

## Automated verification

| Check | Result | Observation |
| --- | --- | --- |
| Gate contract dataset | PASS | 18 fixed cases are present; greetings, symptoms, urgency, harmful requests, out-of-scope questions, and catalog regressions are covered. |
| Gate/policy/generator/use-case suite | PASS | 94 passed. |
| AI Worker + chat API suite | PASS | 1,382 passed, 1 skipped. |
| Ruff (`ai_worker`, `app`) | PASS | No lint errors. |

## Behavioural checks covered by automated tests

| Scenario | Expected route | Automated result | Observation |
| --- | --- | --- | --- |
| Known medication question | `MEDICATION_GUIDE` | PASS | Conversation Gate is bypassed for a catalog-resolved medication question. |
| Vague symptom | `CLARIFICATION` | PASS | RAG retrieval is not invoked; the response asks for details. |
| Specific symptom with active medication | `CLARIFICATION` | PASS | Clean active medication names are shown; medication recommendation and inferred interaction are absent. |
| Harmful instructions | `RESTRICTED` | PASS | The request is blocked before RAG. |
| Explicit active-intake interaction with an approved rule | `ACTIVE_INTAKE` | PASS | The answer includes an approved interaction-rule source. |
| Active-intake interaction without an approved rule | `ACTIVE_INTAKE` | PASS | The answer states that an interaction could not be confirmed and that this does not mean it is safe. |
| Conversation trace | N/A | PASS | `conversation.classify` and `conversation.respond` expose structural metadata only; question text and medication names are excluded with content capture off. |

## Experiment log

| Experiment | Status | Reason / result |
| --- | --- | --- |
| Existing deterministic safety checks | SUCCESS | Urgent health guard, safety policy, and grounded evidence boundaries are covered by unit tests. |
| Conversation Gate prompt-chain contract | SUCCESS | Strict JSON output and four-message history bound are tested with a recording client. |
| Docker readiness check | SUCCESS | `fastapi`, `ai-worker`, `mysql`, `redis`, and `qdrant` were running. The FastAPI container had no `CONVERSATION_*` override, therefore the default OFF flag applied. |
| Live OpenAI evaluation of the 18 fixed questions | NOT RUN | The evaluator would send the stored questions to the OpenAI API. Execution requires explicit approval for that external transmission. |

## Live evaluation metrics

The following metrics are intentionally not populated until the approved live evaluation runs. No synthetic values are recorded.

| Metric | Value |
| --- | --- |
| Gate intent/disposition pass rate | Not run |
| Gate P50 / P95 | Not run |
| End-to-end P50 / P95 | Not run |
| Existing 20-question regressions under flag OFF | Not run against Docker |
| Live LangSmith parent/child span observation | Not run |

## Activation decision

Keep `CONVERSATION_GATE_ENABLED=false` as the default. The implementation and deterministic regressions are verified, but live model classification, latency, and LangSmith observation must be measured before enabling the Gate in a shared runtime.

## Next live-validation procedure

After explicit approval for OpenAI API transmission:

1. Run the 18 fixed questions once through `ConversationGateChain` with the existing `gpt-4o-mini` key and record intent, signal, disposition, and duration.
2. Run Docker with the flag OFF to verify the existing 20-question baseline remains unchanged.
3. Run Docker with the flag ON against the same 18 questions and inspect LangSmith for `conversation.classify → conversation.respond` or a terminal safety response.
4. Record P50/P95, any misclassification, and the activation decision in this file with a follow-up commit.
