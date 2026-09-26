# Vertical Slice 2 — Google/Gemini Capability Matrix

| Capability | Relevance | Status | Evidence / constraint |
|---|---|---|---|
| Gemini Files API | Core source-document representation | ENABLED | Source content hash + persisted Gemini file identity; valid files are revalidated and reused. |
| Gemini PDF document understanding | Core book understanding | ENABLED | Book Map is generated from the original PDF document reference. |
| Structured output | Core map/material contract | ENABLED | JSON response MIME type + Pydantic response schemas for book map and material discovery. |
| Bounded PDF inputs | Required quota/lifecycle protection | ENABLED | Topic/chunk discovery builds an in-memory PDF containing only the persisted page span and sends it inline; no per-topic Files upload. |
| Page-grounded topic spans | Required provenance | ENABLED | Book Map requires page_start/page_end; missing bounds fail explicitly as GEMINI_PROVENANCE_UNAVAILABLE. |
| Usage metadata | Observability | ENABLED when returned | Response usage metadata is logged when available; no usage numbers are fabricated when absent. |
| Implicit context caching | Native Gemini optimization | ENABLED by supported Gemini models | Gemini 2.5+ models provide implicit caching automatically; the application does not depend on a cache hit for correctness. |
| Explicit context caching | Potential repeated-corpus optimization | TECHNICALLY NON-REQUIRED FOR THIS CORRECTNESS PATH | Explicit caching is a beta/paid mechanism and the repaired topic path no longer repeats the full corpus. The correctness boundary is bounded input, not cache availability. |
| File Search | Retrieval + page citations are relevant to provenance | TECHNICALLY BLOCKED AS THE PRIMARY DISCOVERY BOUNDARY | Google File Search returns retrieved chunks and may expose page numbers, but its retrieval API does not provide a deterministic page_start/page_end constraint for a query. Using it as the correctness boundary would allow retrieval outside the persisted topic span and would require a second retrieval architecture. The deterministic bounded-page requirement is therefore implemented with local page slicing instead. |\n| File lifecycle/state | Core reliability | ENABLED | PROCESSING/ACTIVE/FAILED and missing-file handling are explicit. |
| Gemini error classification | Core lifecycle | ENABLED | Stable application codes distinguish quota, rate-limit, auth, file, network/server and response/schema failures. |

## Important distinction

Files API reuse reduces repeated upload/bandwidth work. It does not by itself prove that repeated full-document model input disappeared. The repaired material path therefore uses persisted page bounds and bounded inline PDF inputs.