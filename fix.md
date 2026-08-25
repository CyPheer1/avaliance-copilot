# Avaliance Copilot — RFP Compact Implementation Handoff

## 1. Objective

Implement one user-facing RFP generation mode that is compact, complete, evidence-grounded, professionally formatted, and faster than the previous multi-batch full proposal flow.

The target behavior is:

```text
One requirement-extraction call
        -> one PDF evidence retrieval operation
        -> one structured LLM generation call for exactly six sections
        -> deterministic validation and truncation
        -> at most one targeted repair only for hard evidence/structure failures
        -> compact frontend rendering
```

The system must not trade away requirement coverage, citation integrity, provenance, or explicit clarification behavior merely to reduce latency.

The implementation must be applied only in the local development branch. Do not access AWS, SSH, production Docker contexts, production secrets, or deployment credentials. Do not commit or push until the user reviews the diff and explicitly approves it.

## 2. User requirements

The user wants one mode only. The generated proposal must contain at most six sections, answer the brief directly, remain short but sufficient for the user, avoid repetition and generic prose, be easy to scan, and be generated quickly.

The proposal must preserve the existing evidence-grounding model. Facts from the brief and PDF sources must remain traceable. Unsupported numbers, dates, SLAs, named entities, commitments, and claims must not be invented. The response must distinguish facts, recommendations, assumptions, and questions.

The user-facing path must not expose Brief, Standard, and Full choices. Legacy full-job compatibility may remain internally for the moment, but the normal `/rfp` endpoint and UI must use compact standard mode only.

## 3. Canonical six-section contract

Use these sections, in this exact order:

| Order | Key | Title | Body budget |
|---:|---|---|---:|
| 1 | `executive_summary` | `Synthèse exécutive` | 100 words |
| 2 | `needs_and_objectives` | `Compréhension du besoin et objectifs` | 110 words |
| 3 | `proposed_solution` | `Solution proposée et périmètre` | 150 words |
| 4 | `delivery_and_deliverables` | `Démarche, jalons et livrables` | 120 words |
| 5 | `security_risks_assumptions` | `Sécurité, risques, hypothèses et questions` | 100 words |
| 6 | `avaliance_fit_next_steps` | `Fit Avaliance et prochaines étapes` | 100 words |

The target total is approximately 450–700 words excluding evidence registers, compliance metadata, and other annex metadata. The hard structural limit is six sections in the user-facing compact path.

A section may use `not_applicable` only when the brief genuinely does not require it. Do not fill a section with boilerplate merely to satisfy the section count.

## 4. Files to modify

The primary implementation files are:

```text
service-ia/app/generation/rfp_proposal.py
service-ia/app/generation/prompts.py
service-ia/app/main.py
service-ia/app/schemas.py
service-ia/tests/test_rfp_p0.py
frontend/src/pages/RfpPage.tsx
frontend/src/components/RfpProposalDocument.tsx
frontend/src/components/rfpProposalText.ts
```

Supporting documentation files are:

```text
AGENTS.md
DEVELOPMENT_WORKFLOW.md
docs/RFP_COMPACT_DESIGN.md
```

Do not modify embedding dimensions, model contracts, database migrations, retrieval provenance rules, public security boundaries, or Docker production configuration as part of this RFP compact change.

## 5. Backend orchestration changes

### 5.1 Keep the existing LLM integration

Continue using the existing project helpers:

```python
from .ollama import generate_text, generate_text_async
```

Do not introduce another provider or bypass the current Ollama/LLM configuration. Call A continues to use `generate_text`. The section generation and repair paths continue to use `generate_text_async` with the existing `Settings` object and request ID/stage logging.

### 5.2 Compact section constants

In `service-ia/app/generation/rfp_proposal.py`, define the compact section constants as follows:

```python
STANDARD_SECTIONS_B = [
    {"key": "executive_summary", "title": "Synthèse exécutive", "budget": 100},
    {"key": "needs_and_objectives", "title": "Compréhension du besoin et objectifs", "budget": 110},
    {"key": "proposed_solution", "title": "Solution proposée et périmètre", "budget": 150},
]

STANDARD_SECTIONS_C = [
    {"key": "delivery_and_deliverables", "title": "Démarche, jalons et livrables", "budget": 120},
    {"key": "security_risks_assumptions", "title": "Sécurité, risques, hypothèses et questions", "budget": 100},
    {"key": "avaliance_fit_next_steps", "title": "Fit Avaliance et prochaines étapes", "budget": 100},
]

BRIEF_SECTIONS = STANDARD_SECTIONS_B + [STANDARD_SECTIONS_C[0]]
```

The old 19-section `FULL_SECTIONS` list may remain temporarily for backward-compatible asynchronous jobs. It must not be used by the normal user-facing compact flow.

### 5.3 Bound the evidence sent to the generator

Add a helper equivalent to `_select_generation_packets`:

```python
def _select_generation_packets(
    needs: list[RfpAtomicNeed],
    packets: list[EvidencePacket],
    *,
    per_need: int = 2,
    max_packets: int = 12,
) -> list[EvidencePacket]:
```

The helper must:

1. Prefer one packet for each extracted atomic need.
2. Keep at most two evidence items per selected packet.
3. Stop at twelve packets.
4. Fill remaining capacity from other packets without duplicating requirement IDs.
5. Preserve the original full `packets` list for validation and annex construction. Only the prompt context is bounded.
6. Use immutable/deep copies when reducing evidence lists; do not mutate canonical evidence used by validation.

Serialize the selected prompt packets compactly with `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`. Serialize the atomic needs similarly. Avoid pretty-printed JSON in the main generation prompt because it increases token count.

### 5.4 Make standard mode one generation batch

In `generate_standard_rfp_async`, standard mode must construct:

```python
all_specs = STANDARD_SECTIONS_B + STANDARD_SECTIONS_C
```

Then call `_generate_batch_async` exactly once:

```python
sections, metrics.call_b_ms = await _generate_batch_async(
    request, settings, deadline, all_specs, needs, packets
)
metrics.call_c_ms = 0
```

Do not run standard mode as sequential B and C batches. The valid compact path should contain one main structured generation call, plus Call A and retrieval.

The legacy `full` path may continue to use its existing durable-job batches until it is deliberately removed. Do not allow that path to leak into the normal frontend flow.

### 5.5 Constrain the structured decoder dynamically

Inside `_generate_batch_async`, derive the exact expected keys from `sections_spec`:

```python
expected_keys = [spec["key"] for spec in sections_spec]
```

Copy the base `RFP_STANDARD_SECTION_BATCH_SCHEMA`, then set the section item key schema to an enum containing exactly `expected_keys`. Also set `minItems` and `maxItems` to `len(expected_keys)`.

This prevents local models from returning positional keys such as `"1"`, `"2"`, and so on. The decoder and prompt must both require exactly the canonical keys in order.

The main compact call should use a bounded generation ceiling, currently approximately 2200 tokens. The JSON repair call should use the same bounded schema and a single retry only. Do not add an unbounded retry loop.

### 5.6 Async extraction behavior

Call A remains implemented by the existing synchronous helper for compatibility, but invoke it outside the event loop:

```python
call_a_data, metrics.call_a_ms = await asyncio.to_thread(
    _generate_call_a, request, settings, deadline
)
```

This prevents slow model extraction, especially during cold starts, from blocking other asynchronous RFP requests.

### 5.7 Hard versus soft validation

Add a classifier equivalent to:

```python
_HARD_VIOLATION_MARKERS = (
    "section manquante",
    "preuve inconnue",
    "preuve canonique invalide",
    "citation canonique invalide",
    "citation non pertinente",
    "absente des preuves structurées",
    "valeur factuelle non sourcée",
)


def _is_hard_violation(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _HARD_VIOLATION_MARKERS)
```

The validation loop must split warnings into:

**Hard failures**, which can trigger one repair call:

- missing canonical section;
- unknown or unauthorized evidence ID;
- invalid or orphaned canonical citation;
- citation/evidence mismatch;
- citation that is not supported by its quote;
- unsupported factual number or value;
- missing MUST requirement coverage, where the current validation layer reports it.

**Soft warnings**, which must not trigger an LLM repair call:

- boilerplate phrases;
- repeated n-grams;
- long sentences;
- low information density;
- optional bullets without anchors;
- other stylistic warnings that do not compromise provenance or structural correctness.

Extend `quality.warnings` with soft warnings. Add only hard warnings to `critical_violations` and `violating_keys`. Invoke `_repair_batch_async` only when `critical_violations` is non-empty and sufficient deadline remains.

After repair, classify the repaired section warnings again. A repaired section with no hard warnings is accepted even if it still has soft warnings; those soft warnings are reported. A repaired section with hard warnings remains degraded and must not be silently marked complete.

Do not make style warnings call the LLM again. If deterministic cleanup is available, use it before reporting the warning.

### 5.8 Evidence and annex invariants

Keep the existing evidence hydration and validation design:

- canonical evidence must come from the current request's retrieved PDF packets;
- LLM-selected IDs must be replaced or hydrated with canonical evidence objects;
- citations must remain exact canonical IDs such as `[pdf-001]`;
- only cited sources should be included in the final source register;
- compliance rows must preserve requirement anchors and supporting evidence IDs;
- `evidence_validation_passed` must remain false when evidence-bearing requirements are uncovered.

Do not replace evidence grounding with prompt-only instructions.

## 6. Prompt changes

In `service-ia/app/generation/prompts.py`, update the structured schema and prompt.

### 6.1 Structured output schema

The section batch schema must require:

- `key`;
- `title`;
- `status`;
- `status_reason`;
- `body`;
- `bullets`;
- `assumptions`;
- `questions`;
- `evidence`.

Use these limits:

| Field | Limit |
|---|---:|
| `body` | target 80–120 words; hard character ceiling currently 1800 |
| `bullets` | maximum 3 per section |
| bullet text | maximum 320 characters |
| `assumptions` | maximum 2 per section; maximum 240 characters each |
| `questions` | maximum 3 per section; maximum 240 characters each |
| `evidence` | maximum 4 IDs per section |

Each bullet must contain text and an anchor object. Anchor types are `fact`, `requirement`, `assumption`, and `recommendation`. Evidence items must contain only the canonical evidence ID.

### 6.2 Active generation prompt

The active prompt must say, in substance:

1. Generate exactly the sections provided, in the provided order.
2. Generate one compact paragraph per section, normally 80–120 words and never over the hard budget.
3. Answer the original brief directly and do not repeat the same requirement in multiple sections.
4. Treat the original client brief as authoritative for its facts.
5. Preserve numbers, dates, units, thresholds, SLAs, and named entities exactly when present.
6. Distinguish brief facts, PDF evidence, recommendations, assumptions, and questions.
7. Add canonical PDF citation IDs such as `[pdf-001]` to factual PDF-backed statements.
8. Put only actually used canonical evidence IDs in the section evidence list.
9. Produce at most three useful action/deliverable bullets, two assumptions, and three blocking questions.
10. Avoid generic boilerplate and unsupported commitments.
11. Use sentences of no more than 25 words where practical.
12. Return only valid JSON, with exactly the requested six keys and no Markdown or reasoning text.

The prompt should not say "exactly the six sections" when reused by legacy three-section full-mode batches. Use wording such as "exactly the sections provided below" while the compact standard call provides six sections.

## 7. API behavior

In `service-ia/app/main.py`, the normal `/rfp` endpoint should accept only the compact standard mode:

```python
if request.mode != "standard":
    raise HTTPException(
        status_code=422,
        detail="Only the compact standard RFP mode is supported",
    )
```

The existing `/rfp/jobs` endpoint may remain restricted to `full` for backward-compatible durable jobs, unless the product owner explicitly decides to remove that legacy path. The frontend must not call it for normal compact generation.

In `service-ia/app/schemas.py`, update the default quality section count from 19 to 6:

```python
section_count: int = 6
```

Do not change the response's evidence, coverage, or audit fields.

## 8. Frontend changes

### 8.1 `frontend/src/pages/RfpPage.tsx`

The page must:

- remove the Brief/Standard/Full selector;
- always call the API with `mode: "standard"`;
- label the product as one compact mode with six sections maximum;
- show section count against six;
- display compliance/quality warnings and PDF proof count;
- render `RfpProposalDocument` as the canonical document;
- preserve copy/download actions;
- remove the user-facing asynchronous full-generation flow.

### 8.2 `frontend/src/components/RfpProposalDocument.tsx`

Render one canonical body per section. The renderer must:

- display no more than six sections;
- prefer `section.body`, with `section.summary` only as a compatibility fallback;
- show at most three bullets;
- show at most two assumptions;
- show at most three questions;
- show status pills for `not_applicable` and `requires_clarification`;
- show compact evidence metadata/chips or a verified-reference count;
- not repeat the same prose from legacy `narrative`, `recommendations`, `claims`, `summary`, and `body` fields.

### 8.3 `frontend/src/components/rfpProposalText.ts`

The copy/download text output must follow the same canonical representation:

- title once;
- optional executive banner once;
- first six sections only;
- one body per section;
- at most three bullets, two assumptions, and three questions;
- compact evidence/status metadata;
- no duplicate legacy fields;
- preserve table output only when a table is actually present.

## 9. Tests to update or add

Update `service-ia/tests/test_rfp_p0.py` and related RFP tests.

At minimum, cover:

1. standard mode returns exactly six sections;
2. standard mode calls the main batch generator exactly once;
3. generated section keys are canonical and ordered;
4. per-field limits are enforced;
5. evidence packets passed to generation are bounded and deduplicated;
6. soft style warnings do not trigger repair;
7. hard citation/evidence failures trigger at most one repair;
8. a failed repair produces a degraded response rather than hiding the failure;
9. public `/rfp` rejects non-standard modes;
10. frontend build/type-check passes;
11. legacy full job behavior is either preserved and tested or explicitly removed with a documented migration decision.

The existing standard-mode assertion expecting two batch calls must be changed to expect one. A repair test must use a real hard-warning marker such as `Citation canonique invalide` rather than a generic string such as `Violation!`, because generic style warnings are intentionally soft now.

Recommended local commands:

```powershell
cd "$HOME\Projects\avaliance-copilot-local"
py -3 -m py_compile service-ia\app\generation\rfp_proposal.py service-ia\app\generation\prompts.py service-ia\app\main.py service-ia\app\schemas.py service-ia\tests\test_rfp_p0.py

cd frontend
corepack pnpm run build
```

Run the RFP tests when pytest is available:

```powershell
cd "$HOME\Projects\avaliance-copilot-local\service-ia"
py -3 -m pytest tests\test_rfp_p0.py tests\test_rfp_structured.py tests\test_rfp_json_repair.py -q
```

Do not claim the implementation is fully verified if pytest or an Ollama/Docker integration test has not actually run.

## 10. Acceptance criteria

The change is acceptable only when all of the following are true:

- the normal UI exposes one compact RFP mode;
- the normal `/rfp` path produces at most six canonical sections;
- the valid compact path uses one main structured generation call;
- the prompt context is bounded and deduplicated;
- style-only warnings do not cause an additional LLM repair call;
- hard evidence/structure failures can trigger at most one targeted repair;
- citations, evidence IDs, requirement anchors, and compliance metadata remain valid;
- the renderer and copy/download output do not duplicate prose;
- syntax checks and frontend build pass;
- targeted backend tests pass when the test environment is available;
- no production file, AWS host, Docker production image, production database, or secret is changed;
- no commit, push, merge, or deployment happens without explicit user approval.

## 11. Non-goals and safety boundaries

Do not:

- connect to AWS or SSH from the local implementation task;
- modify the production checkout;
- rebuild or deploy Docker images at this stage;
- change the Ollama model provider or model contract without a separate decision;
- change embedding dimensions or retrieval corpus scope;
- remove citation validation;
- solve verbosity only by blindly lowering token limits;
- add a second LLM provider;
- add automatic GitHub push or automatic production deployment;
- print `.env`, private keys, tokens, passwords, database dumps, or production documents;
- run destructive commands such as `docker compose down -v`, volume deletion, database reset, or destructive migrations.

## 12. Required final report from the implementing agent

After implementation, report:

1. every changed file;
2. the exact mode and section contract implemented;
3. the number of main LLM calls in compact mode;
4. the evidence/context limits;
5. the hard-versus-soft validation behavior;
6. tests actually run and their results;
7. known limitations, especially if Docker/Ollama or pytest was unavailable;
8. confirmation that no commit, push, AWS access, or production deployment occurred.

The implementation is not considered production-ready merely because it compiles. Real RFP examples, regression tests, latency measurements, and evidence-quality checks must be reviewed before promotion.

## References

[1]: https://developers.openai.com/api/docs/guides/structured-outputs "OpenAI Structured Outputs documentation"

[2]: https://docs.ollama.com/capabilities/structured-outputs "Ollama Structured Outputs documentation"

[3]: https://builder.aws.com/content/2wzRXcEcE7u3LfukKwiYIf75Rpw/how-to-get-structured-output-from-llms-a-practical-guide "AWS Builder structured output guide"

[4]: https://github.com/CyPheer1/avaliance-copilot.git "Avaliance Copilot private GitHub repository"
