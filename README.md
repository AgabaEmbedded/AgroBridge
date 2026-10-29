# AgroBridge / FarmVoice

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

`ingest.py` rebuilds the `farmvoice_knowledge` collection and upserts stable-ID chunks, so it is safe to re-run. The first run also downloads `intfloat/multilingual-e5-small` (~470 MB) to the Hugging Face cache. Scanned PDFs need OCR first. Keep source URLs and publication dates in filenames or text, and remove superseded guidance.

## 4. Run the API

```bash
python app.py
# or: uvicorn app:app --host 0.0.0.0 --port 8000
```

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

## Troubleshooting

- **`OSError: [WinError 1114] ... c10.dll`, `WinError 126 ... shm.dll`, or an access violation / silent exit (code 5) in chromadb**: the machine-wide Visual C++ runtime is older than these wheels require. Preferred fix: install the latest *Microsoft Visual C++ Redistributable (x64)*, then restart the shell. Without admin rights, `requirements.txt` installs `msvc-runtime` and `setup_windows_runtime.py` copies its 14.51 DLLs into the directories each native extension searches (`torch/lib`, `chromadb_rust_bindings/`). `rag.py` additionally preloads them via `win_runtime.py` as a safety net.
- **First request/startup is slow**: importing `transformers`/`sentence-transformers` takes ~1–4 minutes on older CPUs; the lifespan hook warms the model before serving.
- **`indexed_chunks` is 0 or low**: run `python ingest.py` and confirm your PDFs contain selectable text (not scans).
- **`MIN_RELEVANCE_DISTANCE`** is a provisional Chroma cosine-distance threshold; tune it on labelled questions.

## Security notes

- `outbound_call.py` reads `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_TO_NUMBER` from the environment. Earlier revisions hard-coded a Twilio SID/auth token; **rotate that auth token** in the Twilio console before pushing anywhere, since it exists in local git history.
- `python app.py` binds `0.0.0.0:8000` with no authentication. Keep it on localhost (`--host 127.0.0.1`) or put it behind a reverse proxy that enforces the provider's webhook signature before exposing it.
- Logs record the transcription event and the model name only; do not add caller numbers or other personal data.

## Notes

- The E5 multilingual model is a starting point, not proof of Hausa quality. Test retrieval with real Hausa/Pidgin questions and trusted answers.
- DeepSeek latency is not guaranteed to fit a 4-second webhook budget; measure end-to-end latency and use a provider-supported async/queued flow if the provider times out.
- For auditability, consider logging question, retrieved source IDs, model/version and latency (avoid storing phone numbers).
