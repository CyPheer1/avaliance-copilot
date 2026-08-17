P0 RFP V7 REJECTED AFTER DIRECT SOURCE-CODE AUDIT

I inspected the actual v7 source code. Do not merge, deploy, start P1/P2, modify the database, change the model, or edit .env.

Work only on the RFP P0 defects listed below. Before modifying code, provide a short plan and exact files to change. Then wait for approval.

VERIFIED DEFECTS

1. Brief LLM extraction is not implemented.
extract_brief_requirements() directly returns _deterministic_extract_requirements().
RFP_BRIEF_EXTRACTION_PROMPT and RFP_BRIEF_SCHEMA are dead code.

Required fix:
- Call generate_text() with RFP_BRIEF_EXTRACTION_PROMPT and RFP_BRIEF_SCHEMA.
- Parse and validate the result with RfpRequirements.
- Verify that atomic source excerpts are exact substrings of the original brief.
- Preserve exact excerpts and character offsets.
- Use deterministic extraction only when the LLM call or schema validation fails.
- Expose/log a non-sensitive extraction_mode: "llm" or "deterministic_fallback".
- Tests must assert generate_text.call_count == 1 for LLM success and assert fallback behavior separately.

2. Planner LLM is not implemented.
_plan_rfp_structure() is entirely deterministic, RFP_PLANNER_PROMPT is unused, and planner_output is never used by the writer.

Required fix:
- Implement a real structured Ollama planner call using RFP_PLANNER_PROMPT and RFP_PLANNER_SCHEMA.
- Validate exactly 19 canonical keys in canonical order.
- Validate covered_need_ids and allowed_source_ids.
- Use deterministic planner only as an explicit fallback.
- Pass the validated planner output to every writer cluster.
- Tests must assert the planner LLM call and prove that its output changes writer inputs.

3. Restore true multi-pass section writing.
The current implementation performs one 1800-token call for all 19 sections and removed _generate_section_cluster().

Required fix:
- Generate bounded canonical clusters, for example:
  1–4, 5–8, 9–12, 13–16 and 17–19.
- Each cluster receives:
  - exact canonical section specs;
  - relevant planner entries;
  - relevant atomic needs;
  - only allowed sources;
  - complete evidence excerpts needed by that cluster.
- Use strict JSON schemas.
- Merge clusters deterministically.
- Enforce a global request budget and per-stage timeouts.
- Record call count and duration per cluster without logging confidential prompts.

4. Activate the deterministic validator.
_validate_proposal_deterministically() currently exists but is never called by production runtime.

Required fix:
- Run it after initial cluster merge and after repair.
- It must reject, not silently sanitize:
  - missing/out-of-order sections;
  - not_applicable without status_reason;
  - missing/duplicate claim IDs;
  - unknown source IDs;
  - invalid claim-kind/source combinations;
  - non-rectangular or empty tables;
  - text outside JSON and <think> content.
- Do not fill missing LLM sections silently and then report perfect quality.

5. Add unsupported factual-value validation.
Detect numbers, percentages, dates, durations, budgets, team sizes, SLAs, capacity values, warranties and commercial commitments.

Rules:
- brief_fact must be supported by an exact brief excerpt;
- internal_evidence must be supported by an exact PDF excerpt;
- unsupported values must be recommendation/assumption/question and explicitly marked “à confirmer”;
- otherwise add a blocking violation.

Add tests for:
- T0 + 2 weeks;
- 99.9% availability;
- 24/7 support;
- fixed team size;
- fixed budget;
- warranty period.

6. Add claim/evidence semantic support validation.
A source ID existing is not sufficient.

Required fix:
- Validate that each internal_evidence claim is supported by its exact cited excerpt.
- At minimum implement deterministic token/entity/number consistency checks.
- Optionally use one bounded LLM critic only after deterministic checks.
- Never give citation_integrity=1.0 simply because no source ID is unknown.
- Reject web evidence as a client-specific fact.

7. Implement the real targeted repair.
RFP_REPAIR_PROMPT is currently dead code.

Required fix:
- Run the full deterministic validator.
- Build one repair request using:
  - exact violations;
  - original generated JSON;
  - canonical section specs;
  - valid sources;
  - brief facts.
- Use RFP_REPAIR_PROMPT.
- Run one repair only.
- Re-run the full validator.
- If violations remain, return a controlled failure/diagnostic. Never silently return a successful deterministic proposal.

8. Make deterministic fallback honest.
The current code catches any generation exception, generates 19 deterministic sections and can return quality.passed=true.

Required fix:
- Do not silently report a normal successful LLM proposal.
- Add explicit response metadata/diagnostic such as:
  generation_mode: "llm" | "deterministic_fallback"
  planner_mode: "llm" | "deterministic_fallback"
  repair_attempted: boolean
- A deterministic fallback must produce visible warnings and cannot score 100%.
- No unsupported commercial statements may appear.

9. Correct the quality model.
The current score measures mostly lexical coverage, section count and absence of warnings.

Required fix:
Implement the specified rubric:
- coverage /20;
- provenance and factual accuracy /25;
- specificity /15;
- solution and delivery quality /15;
- risks/governance/acceptance /10;
- executive writing /10;
- source quality /5.

Critical unsupported facts or fabricated evidence must force passed=false.
Do not use frontend or API defaults of 1.0.

10. Fix frontend parsing and claim rendering.
- Remove client.ts defaults score=1.0, coverage=1.0, citationIntegrity=1.0 and sectionCount=19.
- Missing metrics must render as “Non calculé”.
- Render separate visible groups for:
  brief_fact, internal_evidence, recommendation, assumption, question and future web_evidence.
- Render the warnings themselves, not only their count.
- PDF citations must be interactive and expose document name, physical page, chunk ID and exact excerpt.
- Keep noopener/noreferrer for future web links.
- Do not claim “missions comparables” when the source registry contains documents only.

11. Fix HTTP error semantics.
“Bonjour !” currently produces HTTP 500 in the golden results.
Return a controlled 400 or 422 for empty/trivial briefs through FastAPI, Spring Boot and frontend.

12. Correct tests.
Current tests are misleading:
- extraction and planner tests patch generate_text but do not assert it was called;
- the Playwright “19 sections” test mocks only two sections and expects “2/19”;
- Playwright mocks the API and is not a real full-stack test.

Required tests:
- assert real orchestration call counts;
- assert planner output is consumed;
- assert five writer clusters;
- assert validator is called in production;
- assert one targeted repair;
- assert controlled failure after failed repair;
- test unsupported numbers/commitments;
- use 19 mocked canonical sections for frontend contract tests;
- clearly label mocked UI tests;
- add one real-stack browser validation separately.

13. Rebuild the golden set honestly.
The committed golden_set_results.json contains only IDs 1,2,3,4,8.
IDs 5,6,7 are missing and ID 8 failed with HTTP 500.

Required fix:
- Execute all 8 briefs.
- Do not award 100/100 based only on section count and expected filename.
- Store the complete scoring breakdown and manual-review notes.
- Save sanitized full JSON outputs separately.
- Fail the golden run if any case is missing.

14. Revert unrelated unsafe CORS changes.
CorsConfig.java was changed to wildcard allowed-origin patterns with credentials.
Revert this change unless it is strictly required, approved and security-tested.
Do not modify unrelated application behavior.

15. Clean deliverables.
Do not include:
- .env;
- nested backup ZIPs;
- scratch credentials/tokens;
- stale real_rfp_result.json;
- generated Playwright reports.

The v7 real_rfp_result.json is byte-identical to v6 and is not evidence of the new implementation.

VALIDATION REQUIRED

After implementation run and provide raw outputs:

git status --short
git diff --stat
git diff --check
docker compose config --quiet
docker exec avaliance_service_ia pytest -q /app/tests/
cd backend && ./mvnw test
cd frontend && npm test --if-present
cd frontend && npm run build

Then run:
- one live relevant-PDF request;
- one live no-evidence request;
- one trivial-input request;
- all eight golden briefs;
- one real browser request without API mocking.

Provide correlated runtime metadata:
- request_id;
- extraction mode and duration;
- planner mode and duration;
- writer cluster count and duration per cluster;
- repair attempted/count;
- deterministic fallback used;
- model from actual runtime;
- total duration;
- quality violations.

Do not claim completion based on mocked tests or abbreviated JSON.
Stop after the correction plan and wait for approval before editing.