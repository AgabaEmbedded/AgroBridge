# AgroBridge

Small FastAPI webhook + local Chroma vector index + DeepSeek API.

## 1. Install

Use Python 3.11 or 3.12 in a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

Copy `.env.example` to `.env` and set `DEEPSEEK_API_KEY`.
The API model ID `deepseek-flash` is the current DeepSeek Flash API name; confirm current model IDs and pricing in DeepSeek's official docs before deployment.

## 3. Add documents and index

Put text-based PDF, DOCX, TXT, or Markdown documents in `documents/`, then run:

```bash
python ingest.py
```

Scanned PDFs require OCR first. Use official/credible documents, keep source URLs and publication dates in your filenames or document text, and remove superseded guidance.

## 4. Run the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
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

## Notes

- The first startup/download of the embedding model can take time. Run once before testing live calls.
- `MIN_RELEVANCE_DISTANCE` is a provisional Chroma cosine-distance threshold; tune it using labelled examples.
- The E5 multilingual embedding model is a starting point, not proof of Hausa quality. Test retrieval using real Hausa/Pidgin questions and trusted answers.
- Voice providers may enforce a short webhook deadline. DeepSeek response time is not guaranteed to fit a 4-second budget. Measure end-to-end latency; if the provider's hard timeout is about 5 seconds, you may need a provider-supported async/queued response flow or a faster model/service.
- This MVP returns only the spoken answer. For auditability, extend the API to log the question, retrieved source IDs, model/version, latency, and answer—avoid storing phone numbers or sensitive personal data unnecessarily.
# FarmVoice RAG MVP

Small FastAPI webhook + local Chroma vector index + DeepSeek API.

## 1. Install

Use Python 3.11 or 3.12 in a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure

Copy `.env.example` to `.env` and set `DEEPSEEK_API_KEY`.
The API model ID `deepseek-flash` is the current DeepSeek Flash API name; confirm current model IDs and pricing in DeepSeek's official docs before deployment.

## 3. Add documents and index

Put text-based PDF, DOCX, TXT, or Markdown documents in `documents/`, then run:

```bash
python ingest.py
```

Scanned PDFs require OCR first. Use official/credible documents, keep source URLs and publication dates in your filenames or document text, and remove superseded guidance.

## 4. Run the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
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

## Notes

- The first startup/download of the embedding model can take time. Run once before testing live calls.
- `MIN_RELEVANCE_DISTANCE` is a provisional Chroma cosine-distance threshold; tune it using labelled examples.
- The E5 multilingual embedding model is a starting point, not proof of Hausa quality. Test retrieval using real Hausa/Pidgin questions and trusted answers.
- Voice providers may enforce a short webhook deadline. DeepSeek response time is not guaranteed to fit a 4-second budget. Measure end-to-end latency; if the provider's hard timeout is about 5 seconds, you may need a provider-supported async/queued response flow or a faster model/service.
- This MVP returns only the spoken answer. For auditability, extend the API to log the question, retrieved source IDs, model/version, latency, and answer—avoid storing phone numbers or sensitive personal data unnecessarily.
