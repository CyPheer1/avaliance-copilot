# Avaliance Copilot - End-to-End Code Audit & Architectural Review

## 1. Frontend & UI/UX

**Score: 6/10**

**Review & Findings:**
The frontend uses a modern stack (React 18, TypeScript, Vite, TanStack Query) and provides a clean, responsive UI with features like drag-and-drop document upload and SSE streaming for search results. `DocumentsPage.tsx` is well-implemented, correctly leveraging React Query for state management and mutations.

**Flaws & UX/UI Shortcomings:**
- **Massive Business Logic Leakage:** `SearchPage.tsx` is bloated (~600 lines) because it takes on the responsibility of parsing the LLM's unstructured text output. Functions like `detectAnswerMode`, `identityValues`, `metricRows`, and `architectureRows` use brittle Regular Expressions (e.g., `Indicateur:\s*(.*?);\s*Avant:\s*(.*?)...`) to parse the LLM's response into structured UI components (tables, cards).
- **Brittle Streaming State:** The streaming implementation heavily relies on `useRef` and manual DOM manipulations (`requestAnimationFrame`) to handle incoming tokens, which can lead to race conditions or missed renders compared to standard React streaming patterns.

**Technical Root Cause:**
The backend API returns a raw text stream instead of a structured JSON response (or Server-Sent Events with structured payloads). Because the backend forces the frontend to parse raw Markdown/text strings to build rich UI components, the frontend becomes tightly coupled to the exact phrasing of the LLM and the retrieval fallback mechanisms.

---

## 2. Administration & Dashboard

**Score: 9/10**

**Review & Findings:**
The document administration panel (`DocumentsPage.tsx`) is robust. It properly handles the complete lifecycle of a document (`STORED`, `PROCESSING`, `INDEXED`, `FAILED`). It gracefully prevents uploading files over 20MB and checks file extensions correctly.

**Flaws & Bugs:**
- Error messages from the API are sometimes generic, but the UI handles them reasonably well.
- Deleting or retrying a document blocks the UI temporarily, but it uses optimistic updates / invalidation effectively.

**Technical Root Cause:**
The design here is sound. By delegating the heavy lifting of processing to the backend and tracking state via `react-query`, the dashboard remains responsive and reliable.

---

## 3. Ingestion Pipeline

**Score: 7.5/10**

**Review & Findings:**
The extraction logic (`extraction.py`) intelligently uses `docling` to preserve table structures as Markdown rather than flattening them, and correctly falls back to `pypdf` if `docling` fails. This ensures high-quality text extraction.

**Flaws & Bugs:**
- **Naive Chunking Algorithm:** `chunking.py` implements a custom, regex-based chunking strategy (`\n\s*\n+` for paragraphs and `(?<=[.!?])\s+` for sentences) based purely on character counts.
- **Lack of Semantic Tokenization:** Character-based chunking without a tokenizer (like `tiktoken`) risks splitting context awkwardly or overflowing the LLM's context window since LLMs measure limits in tokens, not characters.

**Technical Root Cause:**
The system uses string manipulation and regex for chunking instead of established NLP libraries (like `spaCy` or `NLTK`) or tokenizer-aware splitters (like LangChain's `RecursiveCharacterTextSplitter`). This makes the chunk boundaries brittle, especially for documents with poor formatting or missing punctuation.

---

## 4. Retrieval Pipeline

**Score: 4/10**

**Review & Findings:**
The retrieval pipeline (`vector_search.py`) implements advanced concepts like Reciprocal Rank Fusion (RRF), cross-encoder reranking, and lexical expansion.

**Flaws & Bugs:**
- **Hardcoded Page Numbers & Brittle Heuristics:** The `_named_project_result_backfill` function contains hardcoded page numbers assuming every PDF follows the exact same template. For example, it hardcodes `section_pages = (3, 4)` for "contexte", `(7, 8)` for "architecture", and `(19, 20)` for "budget".
- **SQL String Matching:** It relies on naive `LIKE '%budget%'` SQL queries mixed with vector search, trying to force keyword matches inside PostgreSQL.

**Technical Root Cause:**
Instead of extracting document metadata (e.g., section headers, table of contents) during the ingestion phase and filtering on those structured fields, the retrieval pipeline attempts to guess document structure at query time using hardcoded heuristics and page numbers. This breaks instantly if a consultant uploads a PDF with a slightly different layout.

---

## 5. Generation & Propositions

**Score: 4/10**

**Review & Findings:**
The generation pipeline (`service.py`) attempts to strictly ground the LLM responses to prevent hallucinations.

**Flaws & Bugs:**
- **Regex-Driven Expert System Overdrive:** `service.py` is bloated (>2300 lines) with highly complex, hardcoded regular expressions designed to intercept the LLM and return deterministic text. Patterns like `_LABELED_TEAM_ROW_PATTERN` and `_PERSON_ROLE_PATTERN` attempt to parse tabular data out of raw chunks before the LLM even sees them.
- **Overly Prescriptive Fallbacks:** The `_deterministic_answer` function attempts to route queries based on hardcoded French intent keywords (e.g., "quelle equipe", "budget consomme") and manually constructs the answer by splicing strings together. If the regex fails, it falls back to the LLM.

**Technical Root Cause:**
The architecture shows a fundamental lack of trust in the LLM's ability to extract information, or an attempt to force structured data extraction on unstructured text *at query time*. Rather than using the LLM for what it is good at (synthesis and extraction), the system wraps it in thousands of lines of fragile regex heuristics. This makes the codebase unmaintainable and highly susceptible to breaking when document phrasing changes even slightly.
