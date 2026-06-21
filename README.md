# CA Drafting Agent

Streamlit and FastAPI app that helps Indian CA firms draft client-facing letters from tax PDFs. The primary UI is now a FastAPI-served browser workbench: upload a PDF, review the generated draft and checklist, reopen saved cases, then ask for revisions in natural language.

All output is draft material for CA review. Verify facts, amounts, deadlines, and client-specific advice before sharing anything externally.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file from `.env.example`:

```bash
GROQ_API_KEY=replace_with_groq_key
APP_API_KEY=replace_with_local_shared_backend_key
ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
API_AGENT_URL=http://localhost:8000/agent/message
```

If an old Groq key was stored locally or shared, rotate it in the Groq console and replace it with the new value.

## Run Backend

```bash
uvicorn app.main:app --reload
```

## Run Frontend

```bash
streamlit run frontend/streamlit_app.py
```

The frontend reads `APP_API_KEY` and `API_AGENT_URL` from Streamlit secrets or environment variables.

## Agent Workflow

1. Enter the client name.
2. Upload a supported tax PDF.
3. Confirm consent that extracted tax text will be sent to Groq for generation.
4. Review the detected document type, draft letter, and verification checklist.
5. Reopen saved cases from the sidebar when needed.
6. Use the chat panel to request revisions.

## Backend Endpoints

- `GET /health`: health check and configured model name.
- `GET /cases`: list persisted drafting cases.
- `GET /cases/{case_id}`: load one persisted case with chat messages.
- `POST /upload`: backwards-compatible single-shot upload endpoint.
- `POST /agent/message`: agent endpoint for document intake and follow-up revisions.

State-changing endpoints require the `X-API-Key` header matching `APP_API_KEY`.

## Supported Document Types

| Document type | Detection markers | Output |
| --- | --- | --- |
| Form 26AS | Form 26AS, Annual Tax Statement, TRACES | Pre-filing client summary letter |
| Income Tax Notice | Income Tax Notice, Section 143, Section 148, Demand Notice | Advisory letter with documents and deadline |
| ITR Summary | Return of Income, Acknowledgement Number, ITR- | Post-filing summary letter |

## Security Notes

- Uploads are limited to 25 MB.
- Uploads must have a `.pdf` filename and PDF file header.
- CORS is restricted through `ALLOWED_ORIGINS`.
- Case data is persisted locally in SQLite under `data/ca_agent.db`; this file is ignored by Git.
- Scanned or image-based PDFs are not supported in v1 because the app uses text extraction only and does not include OCR.

## Troubleshooting

If Groq returns a 429 error, the selected API key has hit a rate limit or quota limit for `llama-3.3-70b-versatile`. Check your Groq console limits, wait for the limit window to reset, or use another Groq API key/project with available capacity.
