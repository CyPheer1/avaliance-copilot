P0 RFP REJECTED — CORRECTIVE IMPLEMENTATION REQUIRED

Do not merge, do not start P1/P2, and do not modify unrelated application areas.

The current implementation is only partially compliant. Fix the following verified P0 defects on the existing branch:

1. Implement actual LLM brief extraction.
- extract_brief_requirements() currently returns _deterministic_extract_requirements() directly.
- Call generate_text() with RFP_BRIEF_EXTRACTION_PROMPT and RFP_BRIEF_SCHEMA.
- Validate with RfpRequirements.
- Use the deterministic extractor only when the LLM call or validation fails.
- Preserve exact brief excerpts and offsets.
- Add tests proving both LLM extraction and invalid-JSON fallback.

2. Implement a real planner stage.
- Add a distinct structured LLM call producing the 19-section plan.
- The plan must include section status, planned claims, allowed source IDs, tables, unresolved questions and covered need IDs.
- The planner must not write final prose.

3. Implement real multi-pass writing.
- Do not request all 19 rich sections in one 1800-token call.
- Generate bounded section clusters, for example 1–4, 5–8, 9–12, 13–16 and 17–19.
- Use the exact RFP_19_SECTIONS specification in every relevant call.
- Merge clusters deterministically and preserve global unique claim IDs.

4. Remove unsafe deterministic commercial inventions.
The fallback must not assert or insert unsupported values such as:
- “100% conforme”;
- T0 + 4/10/12 weeks;
- monthly COPIL;
- weekly COTEC;
- support level 3;
- warranty period;
- “expertise reconnue”.
Convert them to explicit assumptions/questions or omit them unless they are in the brief or an authorized source.

5. Implement the requested deterministic validator.
It must detect and report:
- missing/out-of-order sections;
- missing status_reason for not_applicable;
- unknown source IDs;
- duplicate claim IDs;
- unsupported internal-evidence claims;
- unsupported numbers, percentages, dates, durations, standards, capacities and commitments;
- web evidence used as a client fact;
- malformed/non-rectangular/empty tables;
- duplicated content across sections;
- contradictions where deterministically detectable;
- mixed claim kinds;
- <think> or text outside valid JSON.

Unknown citations must not be silently converted into recommendations.

6. Implement real targeted repair.
- Use RFP_REPAIR_PROMPT.
- Pass the original generated proposal and the exact list of violations.
- Run one repair attempt only.
- Re-run all deterministic validators.
- If still invalid, return a controlled diagnostic/error; do not return a deceptive successful proposal.

7. Correct the quality report.
- Do not give citation_integrity=1.0 when no factual citations exist.
- Do not measure coverage by checking whether any common word appears.
- Add the requested rubric dimensions.
- Quality must fail on any critical hallucination or unsupported commercial commitment.
- The current real output must not score 100%.

8. Fix evidence relevance and claim mapping.
- Do not present every retrieved PDF as a comparable reference.
- A health/HDS RFP must not present unrelated logistics, insurance or energy chunks as proven comparable references.
- Every internal_evidence claim must be atomic and semantically supported by the exact cited excerpt.
- Preserve complete exact excerpts in the evidence registry; do not rely only on a 240-character truncation.
- Keep document_id, document_name, physical page and chunk_id.

9. Complete provenance.
- Register brief sources with stable IDs and exact excerpts/offsets.
- Enforce globally unique claim IDs.
- Validate allowed source types for every claim kind.

10. Fix frontend rendering.
- Render all claims by kind: brief_fact, internal_evidence, recommendation, assumption and question.
- Do not hide claims behind narrative or legacy fields.
- Add clickable PDF citation controls showing document, physical page and chunk.
- Display quality warnings and coverage.
- Replace quality fallbacks of 1.0/19 with “not calculated”.
- Keep loading/error/retry/copy/text export and legacy-response safety.

11. Stop logging the full confidential brief.
- RfpService currently passes request.getDescription() to auditService.log().
- Log request_id, status, duration and non-sensitive metadata only.

12. Strengthen synthetic-data isolation.
- Keep corpus_scope="PDF" for /rfp.
- Add an integration-level guard/test proving production /rfp cannot query MISSION/demo/synthetic data, not only a mocked assert_not_called test.

13. Add missing P0 tests.
At minimum:
- LLM extraction and invalid JSON fallback;
- planner output;
- section cluster writing;
- unique claims;
- unknown citation rejection;
- unsupported number/date/commitment rejection;
- semantic evidence mismatch;
- table validation;
- single repair and controlled failure;
- no-PDF output;
- synthetic runtime isolation;
- backend mappings/audit/timeout;
- frontend claim rendering, PDF citation, no source, malformed response, retry and export.

14. Create the required eight-brief RFP golden set and scoring report.

15. Perform real validation on AWS.
Run and provide unedited outputs for:
- docker compose config
- service-ia pytest
- backend mvnw test
- frontend npm test --if-present and npm run build
- two authenticated /api/rfp/generate calls
- one relevant-PDF case
- one no-relevant-PDF case

For each real call, prove:
- Ollama was actually invoked;
- whether repair was invoked;
- no deterministic fallback was used silently;
- elapsed time;
- model name;
- JSON validity;
- section count;
- evidence relevance;
- quality violations;
- request_id-correlated logs.

Also provide nvidia-smi, ollama ps, VRAM, latency and tokens/s measurements.

Do not claim completion based on mocked tests. Do not edit .env. Remove .env, scratch result files and nested backup ZIPs from any deliverable archive. Commit only the corrective P0 files and produce a final diff/status report.