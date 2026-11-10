# AgroBridge

AgroBridge gives crop farmers a direct way to reach a trusted agricultural AI over a normal phone
call. The farmer speaks in a familiar language and hears a short, evidence-based answer. No
smartphone, app, account or data plan is required on the farmer's side.

A separate Policy Analyzer workflow compares crop-production needs with Nigerian policy,
institutional and delivery evidence. It is used by analysts and programme staff, not by callers.

The system focus is crop production. Livestock questions are redirected outside the product.

## What is in the repository

| Part | Purpose |
|---|---|
| Phone QA agent | Vapi call → speech transcription → conversation router → KB1 answer → KB2 policy check → voice reply |
| Policy Analyzer | Policy Analyst (PA) and Crop Production Analyst (CPA) exchange findings, then synthesis reports gaps |
| KB1 | Crop-production manuals, guides, pest and disease references |
| KB2 | Policies, laws, institutional mandates, budgets and implementation reports |
| Audit | JSONL records of questions, sources, verification and final answers |
| Web UI | React workspace for Policy Analyzer queries and citations |

## Quick start

Python 3.12 is recommended; Python 3.11 also works. On Windows, run the runtime helper after
installing dependencies.

```bash
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_windows_runtime.py      # Windows only
```

Create `.env` from `.env.example`, then set at least:

```env
DEEPSEEK_API_KEY=...
VAPI_PUBLIC_BASE_URL=https://your-public-host.example
ELEVENLABS_VOICE_ID=...
```

Ingest the knowledge bases:

```bash
python ingest.py
```

Start the API:

```bash
python app.py
# or
uvicorn app:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

`indexed_chunks` in `/health` is the KB1 count only. The total is
`kb1_chunks + kb2_chunks`.

## Architecture

```text
Phone call
   │
   ▼
Vapi (telephony, AssemblyAI transcription, ElevenLabs voice)
   │  assistant-request
   ▼
FastAPI /vapi/chat/completions
   │
   ▼
QA graph
   ├─ conversation router
   ├─ crop answer agent (KB1)
   ├─ policy verifier (KB2)  ← high-risk answers only
   ├─ revision (bounded)
   └─ finalise (spoken answer + audit)

Policy Analyzer
   ├─ Policy Analyst (KB2)
   ├─ Crop Production Analyst (KB1)
   ├─ structured exchange (bounded rounds)
   └─ synthesis (gap report + citations)
```

## Main workflows

### Phone QA agent

A caller reaches the Vapi assistant. Vapi returns a transient assistant configuration from the
webhook and sends each turn to the OpenAI-compatible custom-LLM endpoint. The turn is processed by
the QA graph:

- The conversation router handles greetings, short answers, likely speech-recognition errors,
  pending crop questions and clear crop questions.
- Clear greetings and crop questions with an explicit topic use a deterministic fast path and skip
  the AI router.
- The answer agent retrieves evidence from KB1 and writes a short, citation-bound answer.
- The verifier checks policy and safety. General, low-risk answers skip the verifier model call and
  return `NOT_REQUIRED`; pesticide, fertilizer, dose, rate and related advice still run the KB2
  verifier.
- Unapproved advice is revised or replaced with a safe referral.
- Final speech is stripped of document names, page numbers, chunk IDs and citation labels.

The target voice scope is English, Nigerian Pidgin, Hausa, Igbo and Yoruba with natural
Nigerian-accented speech. The transcriber and voice are configured in the transient assistant
returned to Vapi.

### Policy Analyzer

`POST /api/policy-analyzer` runs a separate graph:

- **Policy Analyst (PA)** reads KB2: policies, laws, institutional mandates, budgets and
  implementation reports.
- **Crop Production Analyst (CPA)** reads KB1: practical crop-production needs.
- The agents exchange structured findings over `GAP_MAX_ROUNDS`.
- **Synthesis** returns gaps in four groups:
  - policy coverage
  - implementation
  - institutional
  - evidence

Each gap carries a status (`confirmed_shortfall`, `potential_gap` or `insufficient_evidence`),
a plain-language explanation, the relevant commitment, the practical need, implementation
evidence, institution and citations. Missing evidence is not treated as proof that a policy failed.

## Knowledge bases and ingestion

```text
documents/KB1/                 crop-production material
documents/KB2/                 policy and delivery evidence
documents/KB2/digital_policies/  AI, data-protection and digital-economy policies
```

Chunks are content-addressed, so ingestion is incremental: unchanged chunks are not re-embedded,
and chunks for edited/deleted files are removed.

```bash
python ingest.py                  # sync KB1 and KB2
python ingest.py --kb KB1         # one knowledge base
python ingest.py --kb KB2         # one knowledge base
python ingest.py --drop-legacy    # remove the old single-collection index
```

Important: chunk IDs depend on the chunking configuration. If `chroma_db` was built elsewhere
(for example on Colab with different chunk settings), the local chunk IDs will not match. In that
case ingestion treats the old chunks as stale and rebuilds them. Check the collection counts before
running a full sync.

Document processing:

- PDFs keep page numbers; DOCX/TXT/Markdown do not.
- Chunk size is 1,600 characters with 240-character overlap.
- Each chunk stores document, page, chunk, year, status, category and source metadata.
- Optional sidecar `<file>.meta.json` can override metadata.
- Scanned PDFs need OCR; files with no extractable text are skipped.

Embeddings use `intfloat/multilingual-e5-small` locally (384 dimensions). The index is independent
of the generation model.

## Configuration

All settings are in `.env`; see `.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | generation API key |
| `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` | `deepseek-flash` / `https://api.deepseek.com` | generation provider |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | local embeddings |
| `TOP_K` | `6` | KB hits per QA call |
| `MIN_RELEVANCE_DISTANCE` | `0.15` | cosine-distance cutoff |
| `VERIFIER_ENABLED` | `true` | enable KB2 verification |
| `MAX_REVISIONS` | `2` | revision limit |
| `QA_BUDGET_SECONDS` | `4.3` | legacy telephony budget |
| `QA_DEBUG_BUDGET_SECONDS` | `60` | `/debug/ask` budget |
| `VAPI_QA_BUDGET_SECONDS` | `8.0` | Vapi custom-LLM budget |
| `GAP_MAX_ROUNDS` | `2` | PA/CPA exchange rounds |
| `GAP_TIMEOUT_SECONDS` | `240` | Policy Analyzer budget |
| `GAP_MAX_OUTPUT_TOKENS` | `1200` | per-agent output cap |
| `GAP_TOP_K` | `6` | KB hits per policy agent |
| `DEBUG_API_TOKEN` | empty | token for remote `/debug/ask` |
| `GAP_API_TOKEN` | empty | token for `/api/policy-analyzer` |
| `HISTORY_MAX_MESSAGES` / `HISTORY_TTL_SECONDS` | `8` / `1800` | short-term voice memory |
| `CONVERSATION_AI_ENABLED` | `true` | AI router; deterministic fast path is always used for clear turns |
| `CONVERSATION_AI_TIMEOUT` | `2.0` | router timeout |
| `VAPI_PUBLIC_BASE_URL` | empty | public HTTPS host Vapi calls |
| `VAPI_WEBHOOK_SECRET` | empty | optional `X-Vapi-Secret` check |
| `VAPI_CUSTOM_LLM_SECRET` | empty | optional Bearer check on custom LLM |
| `ELEVENLABS_VOICE_ID` | empty | ElevenLabs voice ID |
| `TRANSCRIPT_CORRECTION_ENABLED` | `true` | optional transcript clean-up |
| `AUDIT_ENABLED` | `true` | write JSONL audit records |

The ElevenLabs API key remains in the Vapi integration. Do not put it in this repository.

## API endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | service status and KB counts |
| `POST /debug/ask` | full QA diagnostics; local requests need no token |
| `POST /api/policy-analyzer` | run Policy Analyzer |
| `POST /vapi/webhook` | Vapi server events and `assistant-request` |
| `POST /vapi/chat/completions` | OpenAI-compatible custom LLM |
| `POST /vapi` | alias for custom LLM base-URL configurations |
| `POST /` | legacy telephony webhook; also accepts Vapi events |

### `POST /debug/ask`

```bash
curl -X POST http://127.0.0.1:8000/debug/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What soil does maize need?","conversation_id":"demo"}'
```

Returns the draft, verification status, revisions, KB hits and citations, timings, audit ID, and
both the answer and `voice_answer`.

### `POST /api/policy-analyzer`

```bash
curl -X POST http://127.0.0.1:8000/api/policy-analyzer \
  -H "Content-Type: application/json" \
  -d '{"query":"Compare national extension commitments with smallholder maize needs.","max_rounds":2}'
```

If `GAP_API_TOKEN` is set, send it as `X-Policy-Token` or the legacy `X-Gap-Token`.

## Frontend

The Policy Analyzer UI is a React + Vite app in `frontend/`.

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` if the API is not on `http://127.0.0.1:8000`. The UI shows the gap
categories, evidence status, citations, an execution trace and the phone call button.

Phone number displayed in the UI: **+1 405 716 9054**.

## Vapi setup

The Vapi phone number's **Server URL** should point to the public base of this service. Vapi sends
`assistant-request`; AgroBridge returns a transient assistant with:

- a custom LLM at `{VAPI_PUBLIC_BASE_URL}/vapi`
- AssemblyAI `universal-3-6-pro` transcription
- ElevenLabs `11labs` voice settings pinned in code
- the AgroBridge first message

Vapi appends `/chat/completions` to the model URL. The endpoint accepts both `/vapi` and
`/vapi/chat/completions` and supports JSON and SSE responses.

Quick checks:

```bash
curl -X POST http://127.0.0.1:8000/vapi/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":{"type":"assistant-request","call":{"id":"demo"}}}'

curl -X POST http://127.0.0.1:8000/vapi/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"agrobridge","stream":false,"messages":[{"role":"user","content":"hello"}]}'
```

For a public tunnel, update `VAPI_PUBLIC_BASE_URL` whenever the ngrok/deployment host changes and
restart the API. Keep Vapi server-event and custom-LLM secrets matched if they are enabled.

## Tests

```bash
python tests/test_conversation.py
python tests/test_transcript_resilience.py
python tests/smoke_test.py --graph qa
python tests/smoke_test.py --graph gap
```

- `test_conversation.py` checks routing, context and direct replies without requiring the LLM.
- `test_transcript_resilience.py` checks ASR recovery, ambiguous turns, clarification and spoken
  output safety.
- `smoke_test.py` is an integration test and calls the real embedding and generation services.

## Troubleshooting

**Windows native-library failure (`WinError 1114`, `c10.dll`, silent exit 5).** Install the latest
Microsoft Visual C++ Redistributable (x64), or run `setup_windows_runtime.py` after installing
requirements.

**First request is slow.** Loading the local E5 model takes time on CPU. The lifespan hook warms it
up; indexing all documents is also CPU-bound. There is no GPU requirement.

**`indexed_chunks` looks wrong.** `/health` reports KB1 only. Add `kb1_chunks` and `kb2_chunks` for
the total.

**Ingestion re-embeds everything.** The index was probably built with different chunking or on
another machine. Content-addressed IDs will not match. Check collection IDs before a full sync; a
targeted append or a fresh rebuild may be preferable.

**Chroma dimension mismatch.** This repository uses E5 384-dimensional vectors. An index built with
another embedding model cannot be queried with this code.

**The phone call cannot reach the API.** Check `VAPI_PUBLIC_BASE_URL`, the tunnel/process, and the
Vapi Server URL. The assistant-request endpoint should return valid JSON.

**Voice sounds uneven.** ElevenLabs settings are pinned in the transient assistant. If cadence is
still uneven, inspect whether Vapi is splitting the response into multiple TTS segments; the
custom LLM returns one streamed completion with word-level deltas.

**No audit records.** Check `AUDIT_ENABLED` and the `logs/` directory permissions.

## Security and data

- `.env`, `resources/`, `documents/`, `chroma_db/`, `logs/` and tooling caches are git-ignored.
- Caller identifiers used for memory are hashed; raw phone numbers are not stored.
- Audio is not stored by AgroBridge.
- Audit records retain question, sources, verification and final wording for review.
- Do not expose `/debug/ask` or `/api/policy-analyzer` publicly without the corresponding tokens.

## License

MIT. See `LICENSE`.
