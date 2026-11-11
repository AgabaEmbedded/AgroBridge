# AgroBridge

AgroBridge gives crop farmers a direct way to reach a trusted agricultural AI without the requirement of having internet or smart phone, over a normal phone
call. The farmer speaks in a familiar language and hears a short, evidence-based answer. No
smartphone, app, account or data plan is required on the farmer's side simply bridging local farmers to AI.

A separate Policy Analyzer workflow compares crop-production needs with Nigerian policy,
institutional and delivery evidence. It is used by analysts and programme staff, not by callers.

The system focus on the crop production part of Farming. Livestock questions are are out of scope for now and redirected outside the product.

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

A caller reaches the Vapi assistant. Vapi returns an assistant configuration from the
webhook and sends each turn to the FastAPI Server. The turn is processed by
the QA graph:

- The conversation router handles greetings, short answers, likely speech-recognition errors,
  pending crop questions and clear crop questions routing them to the right agent.
- Clear greetings and crop questions with an explicit topic use a deterministic fast path and skip
  the AI router.
- The answer agent retrieves evidence from KB1 and writes a short, citation-bound answer.
- The verifier checks policy and safety. General, low-risk answers skip the verifier model call and
  return `NOT_REQUIRED`; pesticide, fertilizer, dose, rate and related advice still run the KB2
  verifier.
- Unapproved advice is revised or replaced with a safe referral to extension officer.
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

The current catalogue contains **112 active documents**: **68 in KB1 (crop production)** and **44 in KB2 (policy knowledge base)**.

| Knowledge base | Scope | Documents |
|---|---|---:|
| **KB1** | Crop-production and related field references | **68** |
| **KB2** | Policy, legal, institutional, budget and implementation evidence | **44** |
| **Total** |  | **112** |

### KB1 document breakdown

| Category | Documents |
|---|---:|
| Crop production | 19 |
| Animal health / livestock reference | 14 |
| Pests and diseases | 10 |
| Water management | 7 |
| Seeds and varieties | 5 |
| Extension | 3 |
| Mechanisation | 3 |
| Research and statistics | 3 |
| Soil and fertiliser | 3 |
| Climate and environment | 1 |
| **Total** | **68** |

KB1 includes legacy animal-health references, but the product scope is crop production; livestock
questions are redirected outside the service.

### KB2 document breakdown

| Category | Documents |
|---|---:|
| Implementation reports | 10 |
| National policies | 9 |
| Budgets and statistics | 6 |
| International frameworks | 6 |
| Laws and regulations | 6 |
| Institutional mandates | 4 |
| Digital, data-protection and AI policies | 3 |
| **Total** | **44** |

### Where the documents come from

The most common issuing organisations in the catalogue are:

| Organisation | Documents |
|---|---:|
| National Agricultural Extension and Research Liaison Services (NAERLS) | 31 |
| Federal Ministry of Agriculture and Food Security (FMAFS), including partner variants | 9 |
| International Institute of Tropical Agriculture (IITA), including Feed the Future variants | 8 |
| Food and Agriculture Organization (FAO) | 7 |
| National Agricultural Seeds Council (NASC) | 6 |
| Federal Republic of Nigeria | 3 |
| Other government, research, development and international sources | 48 |

The catalogue includes extension bulletins, production guides, technical manuals, research reports,
national policies, laws, regulations, budgets, implementation reports and international frameworks.
Most materials are Nigerian; 86 records are Nigeria-specific, 20 are global frameworks or
comparators and 3 are Africa-wide and 3 unknown geography.

For More information refere to /metadata


### Ingestion

Chunks are content-addressed, so ingestion is incremental: unchanged chunks are not re-embedded,
and chunks for edited or deleted files are removed.
103 documents have extractable text; 9 use OCR for text extranction.

```bash
python ingest.py                  # sync KB1 and KB2
python ingest.py --kb KB1         # one knowledge base
python ingest.py --kb KB2         # one knowledge base
python ingest.py --drop-legacy    # remove the old single-collection index
```
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
| `QA_BUDGET_SECONDS` | `4.3` | legacy telephony budget in seconds |
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

## License

MIT. See `LICENSE`.
