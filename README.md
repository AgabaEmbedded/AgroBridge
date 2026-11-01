# AgroBridge

Small FastAPI webhook + local Chroma vector index + DeepSeek API. Voicebip posts call events to `/`; a `turn` event is answered from the indexed agricultural documents.

## 1. Install

Use Python 3.12 (3.11 also works) in a virtual environment:

```bash
python -m venv venv
# Windows PowerShell:
venv\Scripts\Activate.ps1
# macOS/Linux:
# source venv/bin/activate
pip install -r requirements.txt
# Windows only (see Troubleshooting):
python setup_windows_runtime.py
```

Dependencies are pinned to versions verified on Windows 10 x64 + Python 3.12. On Windows, `msvc-runtime` ships the Visual C++ 14.51 runtime that torch 2.14 requires when the machine-wide redistributable is older; see Troubleshooting.

## 2. Configure

Copy `.env.example` to `.env` and set `DEEPSEEK_API_KEY`. `.env` is git-ignored; never commit real keys.

The model ID `deepseek-flash` is served by `https://api.deepseek.com`; the app sends `thinking: {"type": "disabled"}` to keep responses inside the voice webhook's latency budget. Confirm current model IDs and pricing in DeepSeek's docs before deployment.

## 3. Add documents and index

Put text-based PDF, DOCX, TXT, or Markdown documents in `documents/`, then run:

```bash
python ingest.py
```

`ingest.py` keeps the persistent `agrobridge_knowledge` collection in sync instead of rebuilding it: chunk IDs are content hashes, so unchanged chunks are skipped, only new chunks are embedded, and chunks from edited or removed documents are deleted. Re-running it on an unchanged corpus is near-instant. The first run also downloads `intfloat/multilingual-e5-small` (~470 MB) to the Hugging Face cache. Scanned PDFs need OCR first. Keep source URLs and publication dates in filenames or text, and remove superseded guidance.

## 4. Run the API

```bash
python app.py
# or: uvicorn app:app --host 0.0.0.0 --port 8000
```

Logs go to stdout and to `logs/agrobridge.log` (uvicorn access lines included), so failures are diagnosable after the terminal closes.

Run detached from the terminal/session on Windows (survives shell exit):

```powershell
Start-Process -FilePath venv\Scripts\python.exe -ArgumentList '-u','app.py' `
  -WorkingDirectory (Get-Location) -WindowStyle Hidden `
  -RedirectStandardOutput logs\server.out.log -RedirectStandardError logs\server.err.log
```

On macOS/Linux use `nohup venv/bin/python -u app.py >> logs/server.out.log 2>&1 &`.

Test health:

```bash
curl http://localhost:8000/health
```

Example webhook test:

```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{"event":"turn","transcription":"My maize leaves have yellow spots. What should I check?"}'
```

`/health` reports `indexed_chunks`; `null` means the local Chroma index or embedding model failed to load (check the server log).

## 5. Conversation memory

Turns are remembered for the duration of a call so follow-ups ("what about for goats?") keep context.

- Key: `conversation_id`, `call_id`, `call_sid` or `session_id` from the webhook payload. If none is present, a shortened SHA-256 of the caller number is used; raw numbers are never stored. With neither, the turn is answered statelessly rather than sharing memory with other callers.
- Scope: last `HISTORY_MAX_MESSAGES` messages (default 8, i.e. four exchanges) per conversation, expiring after `HISTORY_TTL_SECONDS` (default 1800).
- Storage: process memory only — nothing is written to disk, and memory is not shared across multiple uvicorn workers.

For debugging, `POST /debug/ask` accepts `conversation_id` (and `reset_history: true` to clear it) and returns `history_used`, the number of prior messages sent to the model.

## 6. Debug from the terminal

`POST /debug/ask` answers a question and returns the retrieved chunks, distances, stage and timings. Requests from localhost are always allowed; remote callers need `DEBUG_API_TOKEN` in `.env` and must send it as `X-Debug-Token`.

```bash
python debug_client.py "What causes yellow maize leaves?"
python debug_client.py --top-k 6 "How do I prevent Newcastle disease?"
python debug_client.py            # interactive prompt
python debug_client.py --conversation demo "my name is Sunday"
python debug_client.py --conversation demo "what did I say my name was?"   # remembers
python debug_client.py --conversation demo --reset "start over"
```

The client sends a `conversation_id` on every request so memory works; interactive runs generate one automatically, and `--conversation` reuses it across runs.

Raw HTTP:

```bash
curl -X POST http://localhost:8000/debug/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What causes yellow maize leaves?","top_k":4}'
```

The response reports `stage` (`ok`, `empty_question`, `no_relevant_chunks`, `retrieval_error`, `llm_error`, `empty_completion`), every hit's `distance` and `used` flag, and `retrieval_ms` / `llm_ms` / `total_ms`.

## Troubleshooting

- **`OSError: [WinError 1114] ... c10.dll`, `WinError 126 ... shm.dll`, or an access violation / silent exit (code 5) in chromadb**: the machine-wide Visual C++ runtime is older than these wheels require. Preferred fix: install the latest *Microsoft Visual C++ Redistributable (x64)*, then restart the shell. Without admin rights, `requirements.txt` installs `msvc-runtime` and `setup_windows_runtime.py` copies its 14.51 DLLs into the directories each native extension searches (`torch/lib`, `chromadb_rust_bindings/`). `rag.py` additionally preloads them via `win_runtime.py` as a safety net.
- **First request/startup is slow**: importing `transformers`/`sentence-transformers` takes ~1–4 minutes on older CPUs; the lifespan hook warms the model before serving.
- **`indexed_chunks` is 0 or low**: run `python ingest.py` and confirm your PDFs contain selectable text (not scans).
- **`MIN_RELEVANCE_DISTANCE`** is a provisional Chroma cosine-distance threshold; tune it on labelled questions.

## Security notes

- `python app.py` binds `0.0.0.0:8000` with no authentication. Keep it on localhost (`--host 127.0.0.1`) or put it behind a reverse proxy that enforces the provider's webhook signature before exposing it.
- Logs record the transcription event and the model name only; do not add caller numbers or other personal data.

## Notes

- The E5 multilingual model is a starting point, not proof of Hausa quality. Test retrieval with real Hausa/Pidgin questions and trusted answers.
- DeepSeek latency is not guaranteed to fit a 4-second webhook budget; measure end-to-end latency and use a provider-supported async/queued flow if the provider times out.
- For auditability, consider logging question, retrieved source IDs, model/version and latency (avoid storing phone numbers).
