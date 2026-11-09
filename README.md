# AgroBridge

Two independent AI workflows over a shared local knowledge base, generation model and audit
trail:

1. **Question-Answer (voice):** Voicebip posts farmer questions; the AgroBridge agent answers
   from KB1, a policy verifier checks the recommendation against KB2, and unapproved drafts are
   revised and rechecked (bounded loop).
2. **Policy Analyzer (web API):** a Policy Analyst (KB2) and a Crop Production Analyst (KB1)
   exchange structured findings, then a synthesis node reports policy coverage, implementation,
   institutional and evidence gaps.

The two graph definitions are separate (`agents/qa_graph.py`, `agents/gap_graph.py`); they share
only services (LLM, embeddings, retrieval, ingestion, audit).

## Architecture

```text
Voicebip POST /  ->  QA graph
                       ├─ agrobridge agent  (KB1 search)
                       ├─ verifier agent    (KB2 search)
                       ├─ revision agent    (loop, max MAX_REVISIONS)
                       └─ finalize          (voice-safe answer + audit)

POST /api/policy-analyzer -> Policy Analyzer graph
                       ├─ PA policy analyst        (KB2)
                       ├─ CPA agricultural needs    (KB1)
                       ├─ communicate               (structured messages, GAP_MAX_ROUNDS)
                       └─ synthesis                 (4 finding categories + citations)
```

## Directory

```text
services/
  config.py             env-driven settings
  llm_service.py        JSON structured outputs, validation, retry
  embedding_service.py  local e5 model (query/passage prefixes)
  retrieval_service.py  search_kb1 / search_kb2 / get_document
  document_processor.py page-aware extraction + incremental sync
  audit_service.py      JSONL audit records
agents/
  schemas.py            pydantic contracts
  prompts.py            role prompts
  evidence.py           evidence blocks + citation sanitising
  runtime.py            budgets and timings
  state.py              typed graph states
  qa_agents.py          answer / verifier / revision / finalize
  gap_agents.py         PA / CPA / communication / synthesis
  qa_graph.py           question-answer LangGraph
  gap_graph.py          Policy Analyzer LangGraph
documents/KB1/          agricultural manuals, guides, disease references
documents/KB2/          policy, regulation, budget and implementation documents
ingest.py               sync both knowledge bases
app.py                  FastAPI entry points
debug_client.py         terminal client for /debug/ask
tests/smoke_test.py     integration checks (real embeddings + LLM)
```

## Install

Python 3.12 (3.11 works). Windows: run `setup_windows_runtime.py` after installing requirements
(see Troubleshooting).

```bash
python -m venv venv
venv\Scripts\Activate.ps1            # Windows
pip install -r requirements.txt
python setup_windows_runtime.py      # Windows only
```

Generation uses `deepseek-flash`; embeddings use `intfloat/multilingual-e5-small` locally. They
are configured independently.

## Configure

Copy `.env.example` to `.env` and set `DEEPSEEK_API_KEY`. Nothing is hardcoded in agent code.

| Variable | Default | Purpose |
|---|---|---|
| `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` | `deepseek-flash` / `https://api.deepseek.com` | generation provider |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | local embeddings |
| `TOP_K` | `6` | KB hits per QA agent call |
| `MIN_RELEVANCE_DISTANCE` | `0.15` | cosine-distance cutoff (lower is closer; calibrated on crop questions) |
| `VERIFIER_ENABLED` | `true` | policy verification node |
| `MAX_REVISIONS` | `2` | maximum revision attempts |
| `QA_BUDGET_SECONDS` | `4.3` | hard budget for the voice workflow (Voicebip allows ~5 s) |
| `QA_DEBUG_BUDGET_SECONDS` | `60` | budget for `/debug/ask` (full loop) |
| `QA_ANSWER_MAX_TOKENS` / `VERIFIER_MAX_TOKENS` | `320` / `300` | structured output caps |
| `GAP_MAX_ROUNDS` | `2` | agent communication rounds |
| `GAP_TIMEOUT_SECONDS` | `240` | Policy Analyzer workflow budget |
| `GAP_MAX_OUTPUT_TOKENS` | `900` | per-agent output cap |
| `GAP_TOP_K` | `6` | KB hits per policy-analyst call |
| `DEBUG_API_TOKEN` | empty | required for remote `/debug/ask` |
| `GAP_API_TOKEN` | empty | if set, `X-Policy-Token` (or legacy `X-Gap-Token`) required |
| `HISTORY_MAX_MESSAGES` / `HISTORY_TTL_SECONDS` | `8` / `1800` | in-process voice memory |
| `CONVERSATION_AI_ENABLED` | `true` | AI intent/crop/direct-reply router; deterministic fallback |
| `CONVERSATION_AI_TIMEOUT` | `2.0` | cap for the router call |
| `VAPI_QA_BUDGET_SECONDS` | `8.0` | longer QA budget for Vapi custom-LLM requests |
| `ELEVENLABS_VOICE_ID` | empty | ElevenLabs voice returned in the Vapi assistant config |
| `VAPI_PUBLIC_BASE_URL` | empty | public HTTPS base Vapi uses for the assistant and custom LLM |
| `VAPI_WEBHOOK_SECRET` | empty | optional `X-Vapi-Secret` check on server events |
| `VAPI_CUSTOM_LLM_SECRET` | empty | optional Bearer check on `/vapi/chat/completions` |
| `TRANSCRIPT_CORRECTION_ENABLED` | `true` | normalise noisy ASR before routing |
| `TRANSCRIPT_CORRECTION_TIMEOUT` | `3.0` | cap for the optional correction LLM call |
| `NOISY_TRANSCRIPT_HINT` | `true` | warn the AgroBridge answer prompt about ASR errors |
| `AUDIT_ENABLED` | `true` | JSONL audit trail |

`LLM_TIMEOUT_SECONDS` remains as an advisory ceiling; each agent call is also bounded by the
workflow budget.

## Knowledge bases

```text
documents/KB1/   agriculture: crops, pests, livestock, soil, extension guides
documents/KB2/   policy: strategies, regulations, budgets, implementation reports
```

Ingest (incremental, content-addressed):

```bash
python ingest.py                 # KB1 + KB2
python ingest.py --kb KB2        # one KB
python ingest.py --drop-legacy   # also delete the old single-collection index
```

- PDFs keep page numbers; DOCX/TXT/MD are stored without page numbers.
- Every chunk stores `document_id`, `document_name`, `knowledge_base`, `document_type`, `source`,
  `publication_year`, `page_number` (when available), `category`, `source_path`, `chunk_index`.
- Unchanged chunks are not re-embedded; edited/deleted documents have stale chunks removed.
- Optional sidecar `<file>.meta.json` overrides metadata:
  `{"title": "...", "document_type": "policy", "publication_year": 2024, "category": "livestock", "source": "https://..."}`
- Scanned PDFs still need OCR before ingestion; a file with no extractable text is skipped.

## Run

```bash
python app.py
# or: uvicorn app:app --host 0.0.0.0 --port 8000
```

Logs: stdout and `logs/agrobridge.log`. Audit: `logs/audit-YYYY-MM-DD.jsonl` (one record per
workflow request, with agent outputs, KB citations, verification/revision history and timings).

## Frontend (Policy Analyzer)

The React + Vite interface lives in `frontend/` and calls only `POST /api/policy-analyzer` and
`GET /health`. It presents the four gap categories, evidence status, citations, an expandable
agent execution trace and a `tel:` button for the phone-based Farmer Assistant. Start it with
`cd frontend && npm install && npm run dev`; full setup, CORS and backend notes are in
`build_instructions/frontend_run_instructions.md`.


### `POST /` — Voicebip webhook

Unchanged contract. `turn` runs the conversation router and, when needed, the QA graph with the
voice budget; other events are acknowledged as before (`call.idle_silence` asks the caller to
repeat the question).

```bash
curl -X POST http://localhost:8000/ -H "Content-Type: application/json" \
  -d '{"event":"turn","call_id":"demo-1","transcription":"What are the signs of cassava mosaic disease?"}'
# -> {"response": "...", "text": "..."}
```

**Conversation handling.** Before retrieval, a deterministic router classifies the turn:

- greetings/social openings receive a natural reply and never touch RAG;
- livestock questions are politely declined with a veterinarian/extension referral;
- clear out-of-scope questions are declined;
- a farming/crop question with no crop (e.g. “my leaves are yellow” or “I am preparing land for
  farming”) goes to the answer agent; the agent decides whether a crop follow-up is needed;
- once a crop is named, it is retained from earlier user turns, prepended to retrieval queries and
  used to filter evidence, so the assistant does not re-ask and does not mix crops;
- greetings use “Hello! I am AgroBridge. What can I help you with?” and do not demand a crop;
- specific advice is only returned when KB1 evidence supports it and at least one citation
  survives validation; otherwise the caller is asked for the missing information.

An LLM router makes the intent/crop decision and writes the short reply for greetings, social
turns, livestock redirects, out-of-scope requests and unintelligible turns. Missing a crop is not a
triaging failure; farming questions proceed to the answer agent, which may ask a follow-up itself. The rule-based classifier is
retained only as a fallback when the AI call fails or the latency budget is exhausted
(`CONVERSATION_AI_ENABLED`, `CONVERSATION_AI_TIMEOUT`).

**Noisy speech-to-text.** The router runs after a transcript-normalisation step. Phrase-scoped
deterministic repairs cover the errors observed on live calls (for example `line`→rice,
`mead`→maize, `capitalize`→fertilizer, `family in`→farmer in); an optional LLM corrector handles
other noise and is skipped for greetings, direct replies and already-clean transcripts. A separate
prompt hint tells the AgroBridge answer agent that the text may contain ASR errors and agricultural
mis-hearings. Both mechanisms can be disabled with the environment flags above.

If verification finds a policy conflict that revision cannot resolve, the caller receives a safe
referral instead of the unapproved advice. `NEEDS_REVIEW` answers are returned with a request to
confirm with a local extension officer.

### `POST /debug/ask` — full QA diagnostics

```bash
python debug_client.py "What are the signs of foot and mouth disease in cattle?"
# or
curl -X POST http://localhost:8000/debug/ask -H "Content-Type: application/json" \
  -d '{"question":"...","conversation_id":"demo"}'
```

Returns the draft, verifier verdict (`APPROVED` / `UNAPPROVED` / `NEEDS_REVIEW`), revision count,
KB1/KB2 hits with citations, per-node timings, audit id and both the raw answer and the
`voice_answer`. Local requests need no token; remote requests require `X-Debug-Token`.

### `POST /api/policy-analyzer`

```bash
curl -X POST http://localhost:8000/api/policy-analyzer -H "Content-Type: application/json" \
  -d '{"query":"How well does Nigeria's seed and extension policy match what smallholder maize farmers need?","max_rounds":1}'
```

Returns `report` with `policy_coverage_gaps`, `implementation_gaps`, `institutional_gaps`,
`evidence_gaps` (each item: description, commitment, practical need, implementation evidence,
institution, citations, evidence_status, confidence), plus `communication`, agent findings,
timings and `audit_id`. Each gap is labelled `confirmed_shortfall`, `potential_gap` or
`insufficient_evidence` and includes a plain-language `plain_explanation`; categories with no
evidence-backed gaps are omitted by the UI rather than padded.

### `GET /health`

```json
{"status":"ok","model":"deepseek-flash","indexed_chunks":546,"kb1_chunks":546,"kb2_chunks":254,
 "verifier_enabled":true,"max_revisions":2,"qa_budget_seconds":4.3}
```

## Vapi telephony

Vapi is configured at the phone number's **Server URL**, not with a static assistant. When an
inbound call arrives with no `assistantId`, Vapi sends `assistant-request` to that URL. AgroBridge
returns a transient assistant whose model is `custom-llm` at:

```text
{VAPI_PUBLIC_BASE_URL}/vapi
```

Vapi appends `/chat/completions`, so each caller turn reaches
`POST /vapi/chat/completions` (also accepted at `/vapi` if the URL is configured as a full endpoint) in OpenAI format. The endpoint maps the latest user transcript plus
prior user/assistant messages to the existing AgroBridge QA graph and returns either a normal
`chat.completion` JSON body or an SSE stream (`stream=true`, ending with `data: [DONE]`).

Server events are accepted at both the root `/` and `/vapi/webhook`, so the existing Voicebip
webhook and Vapi can share one public URL. Informational events are acknowledged; `assistant-request`
returns the assistant configuration immediately (well inside Vapi's 7.5 s limit).

Configuration:

```env
VAPI_PUBLIC_BASE_URL=https://your-public-host.example
# Optional; if set, configure the same values in Vapi.
VAPI_WEBHOOK_SECRET=
VAPI_CUSTOM_LLM_SECRET=
```

- The public base must be the HTTPS host Vapi can reach (ngrok or a deployment URL). Update it if
  the tunnel changes.
- The assistant config is generated dynamically, so no custom LLM URL needs to be pasted into the
  Vapi dashboard.
- If the assistant-request payload contains a call id, it is recorded as `conversation_id` in the
  QA audit; otherwise Vapi's message history supplies conversation context.
- Vapi is only the telephony/STT/TTS layer; KB1, KB2, the verifier, audit and conversation logic
  remain in this service.
- The transient assistant requests the ElevenLabs voice `11labs` / `eleven_flash_v2_5` with the
  configured `ELEVENLABS_VOICE_ID`; the ElevenLabs key stays in the Vapi integration, not this repo.
- Vapi custom-LLM requests use `VAPI_QA_BUDGET_SECONDS` (default 8 s) instead of the 4.3 s Voicebip
  budget, because the AI router adds a model call before retrieval/answer generation.

Quick checks:

```bash
curl -X POST http://localhost:8000/vapi/webhook -H "Content-Type: application/json" \
  -d '{"message":{"type":"assistant-request","call":{"id":"demo"}}}'

curl -X POST http://localhost:8000/vapi/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"agrobridge","stream":false,"messages":[{"role":"user","content":"hello"}]}'
```

## Tests

```bash
python tests/smoke_test.py            # retrieval + QA + revision path + Policy Analyzer
python tests/smoke_test.py --graph qa
python tests/smoke_test.py --graph gap
```

They call the real embedding model and LLM, and assert citation containment, revision limits,
communication between PA/CPA and audit records.

## Troubleshooting

- **`WinError 1114` / `1114 c10.dll` / silent exit 5 on Windows:** System32's Visual C++ runtime is
  older than torch/chromadb expect. Install the latest *Microsoft Visual C++ Redistributable (x64)*,
  or rely on `msvc-runtime` + `setup_windows_runtime.py` (the embedding service also preloads it).
- **First request is slow:** importing `transformers`/`sentence-transformers` takes 1–4 minutes on
  older CPUs. The lifespan hook warms the model; the first real turn is then ~2 s.
- **`indexed_chunks` is 0:** run `python ingest.py`. Files must be under `documents/KB1` or
  `documents/KB2`; files directly in `documents/` are ignored.
- **Scanned PDFs:** no extractable text means the file is skipped; OCR it first.
- **Old index:** the pre-multi-agent `agrobridge_knowledge` collection is unused; delete it with
  `python ingest.py --drop-legacy`.
