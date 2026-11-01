# Running the AgroBridge Gap Analysis frontend

This guide covers the React + Vite interface for the **Gap Analysis** workflow. The Farmer
Question-Answer system remains telephone-only (Voicebip); the UI only exposes it through a
`tel:` call button.

## 1. What the app does

- Starts policy/needs gap analyses through `POST /api/gap-analysis`.
- Shows the synthesis report split into policy coverage, implementation, institutional and
  evidence gaps, each with evidence status, confidence and citations.
- Shows an execution trace built from the backend's structured outputs: GA1 policy findings,
  GA2 agricultural-needs findings, the agent-to-agent messages and synthesis timings.
- Keeps analysis history in the browser (`localStorage`), because the backend has no
  conversation store.
- Provides a "Call Farmer Assistant" button (`tel:+2342013502062`, shown as
  `+234 201 350 2062`).

## 2. Prerequisites

- **Backend:** Python 3.12 virtual environment with the project requirements installed, and the
  knowledge bases ingested.
- **Frontend:** Node.js 20+ and npm. Verified with Node **24.22.2** / npm **11.19.1**.

If Node is not installed and you cannot install it system-wide, a portable build works:

```powershell
# Windows, no admin required
mkdir .tools
curl.exe -L -o .tools/node.zip https://nodejs.org/dist/v24.22.2/node-v24.22.2-win-x64.zip
tar -xf .tools/node.zip -C .tools
Rename-Item .tools/node-v24.22.2-win-x64 .tools/node
$env:PATH = "$PWD\.tools\node;$env:PATH"
node --version
```

`.tools/` is git-ignored. On macOS/Linux use the official installer or nvm.

## 3. Start the backend

From the project root:

```bash
# Windows
venv\Scripts\Activate.ps1
# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
python setup_windows_runtime.py     # Windows only (VC++ runtime workaround)
python ingest.py                    # KB1 + KB2 (incremental)
python app.py                       # http://127.0.0.1:8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","model":"deepseek-flash","kb1_chunks":546,"kb2_chunks":254,...}
```

**CORS:** the backend allows the Vite dev origins by default
(`http://localhost:5173`, `http://127.0.0.1:5173`, and the `:5174` fallbacks). Override with a
comma-separated `FRONTEND_ORIGINS` in `.env` and restart the backend if you serve the frontend
from another origin.

```env
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## 4. Start the frontend

```bash
cd frontend
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
npm install
npm run dev
```

Open <http://127.0.0.1:5173>.

`.env` (optional values):

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
# VITE_GAP_API_TOKEN=          # only if backend GAP_API_TOKEN is set
```

If npm reports that `esbuild`'s install script was not run (npm 11 `allowScripts` policy):

```bash
node node_modules/esbuild/install.js
npm run dev
```

Production build:

```bash
npm run build      # writes frontend/dist
npm run preview    # serves the build locally
```

For a static deployment, serve `frontend/dist` from any web server and set
`VITE_API_BASE_URL` at build time to the public backend URL; add that frontend origin to
`FRONTEND_ORIGINS`.

## 5. Using the interface

1. **New analysis** in the sidebar (or pick an example on the empty state).
2. Type a policy question, choose **discussion rounds** (0–3; default 1 for speed) and press
   **Run analysis**. A run typically takes 30–90 seconds.
3. The report appears with four sections. Each gap shows description, policy commitment,
   agricultural need, implementation evidence, responsible institution, citations, an evidence
   status badge (confirmed shortfall / potential gap / insufficient evidence) and confidence.
4. Expand **Agent execution trace** for the actual structured outputs of GA1, GA2, their message
   exchange and synthesis timings. These are the completed run's backend outputs, not invented
   activity; the API does not stream live events yet.
5. Click any citation (or **Sources & citations**) to inspect the knowledge base, document,
   page and chunk recorded by the backend.
6. **History** is stored locally in the browser. Deleting a thread removes it locally only.
7. Follow-up questions start **new, independent** analyses. The backend gap endpoint is
   stateless, so earlier agent context is not carried into the new run; the thread is kept for
   reference.
8. The telephone button is the only route to the Farmer Assistant.

## 6. API contract used

Only existing backend endpoints are called:

| Method | Path | Used for |
|---|---|---|
| `POST` | `/api/gap-analysis` | Run an analysis (`{"query": "...", "max_rounds": 0-4}`); optional `X-Gap-Token` |
| `GET` | `/health` | Sidebar connection status and KB chunk counts |

Response fields consumed: `report` (summary, four gap arrays, limitations, citations),
`policy_findings`, `needs_findings`, `communication`, `rounds`, `timings`, `audit_id`.

The frontend does **not** call the Voicebip webhook, `/debug/ask`, or any document endpoint.

## 7. Backend changes made for this frontend

- Added CORS middleware with env-driven origins (`FRONTEND_ORIGINS`). No endpoint, schema or
  workflow behaviour changed.
- No new API endpoints were invented.

## 8. Tests performed

- `npm run build` — Vite 5.4.21, 1665 modules transformed, `dist/` emitted (JS 272 kB / 85 kB gzip).
- Backend `GET /health` from the browser — connected, KB1 546 / KB2 254 chunks.
- Live analysis through the UI (query: *"Identify gaps between Nigeria's agricultural extension
  policy and livestock disease control needs"*, 1 round):
  - four sections rendered, 2 gaps each (policy coverage, implementation, institutional, evidence);
  - all three evidence-status badges present; citations shown per gap;
  - execution trace showed GA1/GA2 findings, 4 structured agent messages, timing blocks and
    retrieved evidence;
  - "Sources & citations" dialog listed 15 citations with KB/document/page/chunk, and selecting one
    showed copy-citation plus the note about the missing document endpoint.
- History persisted in `localStorage` and survived a full page reload; the saved analysis was
  re-opened from the sidebar.
- Mobile viewport 390×844: sidebar hidden, menu dialog opened with history/new analysis/phone
  number, no horizontal overflow; call link `tel:+2342013502062`.
- Offline simulation: submitting with the network disabled showed the error card with Retry and
  Dismiss; Dismiss cleared it.
- Console: only the aborted duplicate `/health` request caused by React StrictMode's double mount;
  no application errors.

## 9. Outstanding backend work (identified, not implemented)

1. **Live execution events.** The graph currently returns everything after synthesis. For a live
   trace, add a streaming route (e.g. `POST /api/gap-analysis/stream`) that emits
   `text/event-stream` events such as
   `{"stage":"ga1","status":"completed","findings":{...}}`, `{"stage":"communication",...}`,
   `{"stage":"synthesis",...}`. The graph can publish these from node wrappers or via
   `graph.astream`/callbacks. The UI already labels the trace as a completed run and can be
   switched to subscribe when available.
2. **Source text inspection.** `services/retrieval_service.get_document(document_id, page)`
   exists, but no HTTP route exposes it, and gap citations do not include `document_id`.
   Minimal change: include `document_id` in the citation metadata returned by the gap workflow
   and add `GET /api/documents/{document_id}?page=N` returning the page text. The citations panel
   currently shows KB/document/page/chunk only.
3. **Server-side conversation history.** Not supported. The UI persists threads in
   `localStorage`; a backend history store would be needed for cross-device history.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says "Backend offline" | Start `python app.py`; confirm `curl http://127.0.0.1:8000/health` |
| Browser blocks requests (CORS) | Add the frontend origin to `FRONTEND_ORIGINS` and restart the backend |
| `node`/`npm` not recognised | Prepend the portable Node directory to `PATH` (section 2) |
| npm install fails on `esbuild` | Run `node node_modules/esbuild/install.js` |
| Analysis takes long / errors after ~4 min | Expected ceiling for the gap workflow; retry or reduce discussion rounds |
| `403` on analysis | Backend `GAP_API_TOKEN` is set; provide `VITE_GAP_API_TOKEN` |
| Empty/zero results | Ingest documents (`python ingest.py`), then check `/health` counts |

## 11. Limitations

- No live streaming (see section 8); the running card does not claim per-agent progress.
- Citation inspection is metadata-level until the document endpoint exists.
- History is per-browser and capped at 20 threads.
- Gap analyses are independent runs; no conversational context is sent to the backend.
- The UI is for gap analysis only; farmer advice remains phone-based.
