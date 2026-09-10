# Source-backed interaction retrieval and session reference design

## Goal

Preserve the chatbot's evidence-first safety boundary while improving three
observed gaps: explainable handling of interaction questions without direct
evidence, same-session references to a user's registered intake, and official
medication-guide priority for product-name drug-food questions.

## Evidence from the 20-question evaluation

1. `마그네슘–아연` and `비타민 D–칼슘` produced raw Qdrant candidates, but
   no candidate passed the verified interaction-pair gate.
2. The active `interaction_annotations.yaml` contains approved annotations for
   fexofenadine-fruit juice, warfarin-vitamin K, warfarin-metronidazole,
   acetaminophen-alcohol, and calcium-iron only. It does not declare
   magnesium-zinc or vitamin D-calcium.
3. `ChatRepository._session_reference_from_history` currently creates session
   memory only from `MEDICATION_PRODUCT_GUIDE` chat sources. An interaction
   answer built from a user's registered medication and supplement has no
   reusable structured reference for a following `그중` question.
4. The use case deliberately skips `MedicationGuideRepository` lookup for an
   interaction pair. Therefore a product-name drug-food question such as
   `타이레놀과 술` reaches RAG before the official product guide.
5. The dose-escalation implementation intentionally returns
   `CLARIFICATION + RESTRICTED`; the fatigue triage returns a safe general
   guidance response without a product recommendation. The evaluation YAML did
   not model those deliberate semantics.

## Non-goals

- Do not infer a clinical interaction merely because two ingredients co-occur
  in a document.
- Do not add product- or ingredient-specific conditions in Python code.
- Do not use a previous chat session as a source of medical facts.
- Do not convert an evidence-gap response into a claim that a combination is
  safe.
- Do not introduce a new database table or migration for this work.

## Design

### 1. Verified pair evidence and contextual candidates

`interaction_pair_keys` remains the only eligibility condition for a direct
interaction claim. The retriever will retain exact-pair, entity, and semantic
candidate diagnostics, but candidates without a verified pair key are marked
contextual and cannot satisfy `MedicationEvidenceCoverage` for
`INTERACTION`.

The response path for a missing verified pair is unchanged: it produces an
evidence-gap response with `RESTRICTED` status. The response may state that
the current knowledge base lacks a direct pair source and direct the user to
an official information source, but it must not say that the pair is safe.

New pair metadata can only enter the collection through a source-backed data
declaration: a reviewed document annotation or a reviewed manifest-derived
pair. The indexing test must prove that the declared source document contains
both approved entities. This keeps future data additions out of application
logic.

### 2. Registered-intake and same-session references

The current-session reference builder will produce typed reference entities
from the most recent assistant response only when that response has an
eligible, persisted source:

- `PATIENT_SAVED_FIELD` contributes its medication name as `DRUG`.
- `USER_SUPPLEMENT` contributes its supplement name as `SUPPLEMENT`.
- Existing `MEDICATION_PRODUCT_GUIDE` handling continues to contribute one
  `PRODUCT_NAME` drug reference.

It will preserve the source message boundary and return no reference when a
candidate source cannot be resolved to a current-session message. The maximum
reference size remains four entities. `그중` expands only these typed names;
the normal catalog and active-intake context then revalidate them before
planning a search.

The active-intake summary remains an `INTERACTION` route when the user asks
for interaction priority. `ACTIVE_INTAKE` stays available for non-interaction
care-episode guidance; it is not forced merely to satisfy the evaluation file.

### 3. Evaluation contract semantics

The fixed YAML is a behavior contract, not a copy of enum names from an older
design. It will be corrected as follows:

- Personal dose increase: expected `CLARIFICATION`, `RESTRICTED`, and no
  dosage-increase instruction.
- Fatigue recommendation: expected `GENERAL_GUIDANCE`, `SAFE`, and explicit
  triage/no-personal-product-recommendation markers.
- Registered-intake summary: expected `INTERACTION`, with patient medication
  and supplement source requirements.
- Magnesium-zinc and vitamin D-calcium: expected `RESTRICTED` while no
  source-backed direct pair is present; the contract requires no false safety
  claim. A future approved pair annotation can raise these cases to a direct
  interaction expectation.
- Product-name drug-food questions: require a medication guide whenever an
  eligible guide exists, with RAG remaining supplementary.

### 4. Product-name drug-food guide priority

Before RAG-derived answer assembly, an interaction question with a resolved
product or brand alias and a food entity queries `MedicationGuideRepository`.
An ambiguous guide still triggers the existing clarification path. A found
guide is an authoritative source for guide-supported caution and usage facts;
RAG chunks remain available only for interaction evidence not contradicted by
the guide. Ingredient-only drug-food questions retain existing RAG behavior.

## Interfaces and files

| Responsibility | Files |
| --- | --- |
| Interaction evidence eligibility and diagnostics | `ai_worker/rag/retrievers/medication_knowledge_retriever.py`, `ai_worker/domain/medication_evidence_coverage.py`, retriever/domain tests |
| Source-backed pair declaration and index validation | `data/knowledge/manifests/interaction_annotations.yaml`, `ai_worker/rag/metadata/interaction_annotation_registry.py`, metadata/indexer tests |
| Same-session source-to-entity projection | `app/repositories/chat_repository.py`, `app/tests/chat_apis/test_chat_repository.py`, session-memory tests |
| Product-name drug-food guide priority | `ai_worker/use_cases/answer_medication_question.py`, use-case tests |
| Evaluation contract | `data/knowledge/evaluation/chat_safety_retrieval_queries_v1.yaml`, evaluation tests |

## Verification

Each implementation unit follows red-green-refactor:

1. A missing verified pair must remain ineligible for a direct interaction
   response even if broad candidates exist.
2. A reviewed annotation must produce an interaction-pair key at indexing;
   an undeclared pair must not.
3. A `그중` question in the same session resolves only registered medication
   and supplement sources from the immediately preceding relevant assistant
   response. A separate session returns no reference.
4. `타이레놀과 술` uses the official product guide if present; an
   ingredient-only drug-food question does not fabricate a product guide.
5. The evaluation YAML validates the updated route and safety-status semantics.
6. The focused suites, all `ai_worker` tests, affected `app` tests, and Ruff
   must pass before each corresponding commit.

## Commit boundaries

1. Existing tested answer-format and duplicate-disclaimer removal changes.
2. Verified-pair/contextual-candidate diagnostics and contract alignment.
3. Registered-intake session-reference projection.
4. Product-name drug-food official-guide priority.

## Implementation verification

- Direct interaction evidence remains strict. The magnesium–zinc and vitamin D–calcium typo cases now deliberately use `NO_SOURCE` with `RESTRICTED`; broad Qdrant candidates cannot become a direct interaction claim.
- A latest same-session assistant answer can contribute its persisted `PATIENT_MEDICATION` and `PATIENT_SUPPLEMENT` sources as typed `DRUG` and `SUPPLEMENT` reference entities. A new session receives no prior-session reference.
- A product-name drug–food question queries the official medication guide using the resolved product name before answer assembly. RAG evidence remains a separate supplementary `PUBLIC_KNOWLEDGE` source.
- The 20-case evaluation contract now records personal dose escalation as `CLARIFICATION` plus `RESTRICTED`, fatigue triage as `GENERAL_GUIDANCE` plus `SAFE`, and active-intake summarization as `INTERACTION` with patient-source requirements.
- Automated verification: 109 targeted AI Worker tests, 13 chat repository tests, Ruff, and `git diff --check` passed on 2026-09-09.
