# EduTool

EduTool is a Vue and FastAPI study workspace for uploaded PDFs. It currently supports:

- Username/password registration and secure cookie sessions
- User-owned PDF uploads and page-by-page text extraction
- Persistent old-document history
- Persistent document-chat history
- Source-grounded OpenRouter chat, summaries, and translation prompts
- Browser text-to-speech that continues through document pages
- Responsive reader with extracted text, summary, translation, and chat tools

## Run locally

The local development path uses SQLite and does not require Docker.

```powershell
cd backend
python -m pip install -e .
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev:host
```

Open http://localhost:5173.

## Configure AI

Set a newly issued OpenRouter key in the ignored `backend/.env` file:

```dotenv
OPENROUTER_API_KEYS=your-first-key,your-second-key,your-third-key
OPENROUTER_MODEL=google/gemini-2.5-flash
```

Use distinct, authorized keys separated by commas. Duplicate values are ignored, and retryable provider failures move to the next configured key. Do not commit `.env` files or reuse the previously exposed key. Without a configured key, uploads, accounts, history, and TTS still work; AI requests return a configuration message.

## Docker Compose

Start Docker Desktop first, then run from the repository root:

```powershell
docker compose up --build
```

Compose provides Vue, FastAPI, PostgreSQL, Redis, and MinIO. Local non-Docker development uses SQLite for faster setup.
