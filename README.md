# EduTool

Vue/FastAPI study workspace with user-owned PDF/DOCX documents, cookie authentication and recovery codes, persistent document chat, language-aware summaries and text-to-speech, translation, and a 10-question Check Me quiz with per-document question history.

## Local setup (Python 3.11+)

Use the workspace virtual environment, not a different global interpreter. From the repository root, create it only if it does not already exist:

```powershell
python -m venv .venv
cd backend
..\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Set local configuration in the ignored backend environment file (never commit credentials). Settings are loaded relative to the backend source; environment variables override the file. A new local setup needs:

```dotenv
DATABASE_URL=sqlite:///./edutool.db
UPLOAD_DIR=uploads
SESSION_SECRET=replace-with-a-long-random-secret
COOKIE_SECURE=false
OPENROUTER_API_KEYS=your-authorized-key
OPENROUTER_MODEL=google/gemini-2.5-flash
```

The database defaults to PostgreSQL, **not SQLite**, unless configured. Relative database/upload paths are relative to the process working directory: run the following from the backend directory consistently. Do not change paths when upgrading an existing installation.

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev:host
```

Open http://localhost:5173. Local API: http://127.0.0.1:8001/api/v1. CORS permits localhost and 127.0.0.1 on port 5173; use one hostname consistently for cookies.

## Safe database upgrades

Migrations are in [backend/alembic.ini](backend/alembic.ini), from the baseline through `0003_language_quiz_recovery`.

1. Back up the configured database **and uploads** before upgrading. Coordinate downtime for writes. For SQLite, use its backup API or copy the database only while writers are stopped; do not copy an active WAL database as a lone file. PostgreSQL needs a verified database backup.
2. Install the updated backend dependencies in the interpreter that will run the API.
3. Run `python -m alembic upgrade head` from the backend directory with the same `DATABASE_URL` as the API. Run one migrator before starting workers.
4. Run `python -m alembic current`; expected revision is `0003_language_quiz_recovery`.
5. Start/restart the API under operator control. Startup checks the revision and does **not** silently create/alter schema.

Fresh databases run both revisions. The baseline inspects/adopts a complete unversioned legacy schema in place; **no manual stamp is necessary**. Baseline-stamped databases also upgrade normally. Already-added `file_hash` columns and the expected unique index are adopted without resetting rows. Existing duplicate legacy rows remain intact; lazy upload-time backfill hashes only one canonical row per user/content and leaves other duplicates nullable.

Migration refuses incomplete baseline tables, missing required columns, a conflicting named index, or duplicate non-null hashes rather than silently modifying user data. Adoption is not an exhaustive schema-drift audit: review custom constraints/types manually. Downgrades that would remove user tables/hashes are deliberately disabled. Offline SQL generation is unsupported because adoption requires schema inspection. Never delete the database or volumes to upgrade.

## Documents and history

All routes below have the `/api/v1` prefix and require an authenticated owner:

| Endpoint | Behavior |
| --- | --- |
| `POST /documents` | PDF or DOCX upload, maximum **25 MiB** (25 × 1024 × 1024 bytes). New content: 201 and `existing: false`. Identical bytes for the same user: 200 and the canonical document with `existing: true`, regardless of filename. |
| `DELETE /documents/{id}` | Delete an owned document, extracted pages, quiz history, associated conversations/messages and its expected upload path. |
| `DELETE /documents` | Clear owned documents and their associated chats/files; preserve other users and legacy unattached chats. |
| `DELETE /conversations/{id}` | Delete one owned conversation and its messages, not its PDF. |
| `DELETE /conversations` | Clear every chat for the current user, including unattached legacy chats. |

Successful deletes return 204; missing/foreign individual IDs return 404. Missing physical files are tolerated. Database deletion is transactional; filesystem cleanup follows commit and is not atomic with the database. An OS permission/locking failure can leave a file requiring operator cleanup. Uploads are stored locally; Redis and MinIO are not used for document storage in this iteration.

### Investigating 405 DELETE / 404 quiz

Check the **actual listener** at `/openapi.json`, not just source files. It must advertise DELETE for both collection and individual document/conversation routes, and POST for `/api/v1/documents/{document_id}/quiz`. A missing prefix, wrong API port/proxy target, or stale worker can produce route errors. An advertised quiz route can still return 404 for an absent/non-owned document ID. Re-authenticate against the correct backend and check the response detail. Do not add unprefixed aliases to mask an incorrect frontend API target.

## Grounded AI behavior

`OPENROUTER_API_KEYS` accepts comma-separated distinct authorized keys. Retryable failures try the next configured key. Provider bodies/credentials are not returned in errors. Without a key, non-AI features still work; AI calls return 503. Configure HTTPS and `COOKIE_SECURE=true` for deployment.

- `POST /chat` requires a selected owned document, optionally a page and matching owned conversation. Follow-ups resolve references from recent history while retaining source-only factual grounding.
- History includes only complete user/assistant pairs, ordered by timestamp and ID. Defaults: **12 messages / 16,000 characters**; configurable with `CHAT_HISTORY_MESSAGES` and `CHAT_HISTORY_CHARS`. These are character budgets, not tokenizer-exact token limits.
- Structured classifications are `answerable`, `unrelated`, or `gibberish`. Rejected requests get deterministic refusal text and up to two suggested study questions. Invalid classifications or contradictory/empty answer contracts fail closed with 502 and save no turns.
- `operation: "summary"` or `"translation"` on `/chat` uses only selected source context, receives no chat history, and creates no conversation/messages. Quiz generation is likewise non-persisting. Legacy utility messages are not automatically distinguishable and are not rewritten.
- New uploads are classified as English, Arabic, or Swahili. Chat, summaries, refusals, quiz content, text direction, and browser speech language follow the document language. Translation follows its explicitly selected target language.
- Document context is capped at `DOCUMENT_CONTEXT_LIMIT` (default 30,000 characters). Whole-document chat uses the beginning of the extracted text, not retrieval across arbitrarily long documents. Select a page for precise grounding.

### Check Me quiz

`POST /documents/{id}/quiz` accepts `{"page_numbers":[1,2],"question_count":10}`. It returns exactly 10 distinct questions with four nonempty distinct options, integer `correct_index` (0–3), explanation and selected `source_page`.

Questions should test concepts, application and misconceptions—not author names, document titles, publication data or page-location trivia. Prompt instructions and deterministic metadata-pattern checks enforce this; invalid JSON/shape, duplicates, invalid source pages and detected metadata trivia trigger **one complete repair**, then 502. A provider outage is not retried as a content repair. These checks do not prove semantic correctness, entailment or coverage, and metadata detection is English-oriented; review generated answers against the PDF.

Select 1–300 pages; the frontend initially selects the whole document. Every selected page needs at least 80 extracted characters. Context is divided across the selected pages within `QUIZ_CONTEXT_LIMIT` (default 45,000 characters), rather than silently excluding later pages. Generated question text and source pages are stored per document and supplied to later generations to prevent exact repeats; answers and scores remain client-side.

## Password recovery

Registration returns a recovery code once and the signed-in workspace keeps it visible until dismissed. Store it outside the app. `POST /auth/reset-password` accepts username, recovery code, and a new password. Recovery codes are stored only as SHA-256 hashes and remain valid for future resets; deployment-level rate limiting is still required for an internet-facing service.

## PDF extraction and OCR limits

The parser validates signature/encryption/page count, tries pypdf and pdfplumber layout/table extraction, normalizes repeated lines/table rows and recognizes simple two-column gutters. Only pages with fewer than 40 extracted characters receive OCR via pypdfium2 and RapidOCR/ONNX Runtime. No external Poppler/Tesseract installation or OCR service is required.

| Setting | Default |
| --- | --- |
| `PDF_MAX_PAGES` | 300 |
| `PDF_MAX_OCR_PAGES` | 30 per upload; split larger scans |
| `PDF_OCR_MAX_PIXELS` | 4,000,000 per rendered page |
| `PDF_OCR_MAX_DIMENSION` | 2,400 pixels per side |

OCR initializes lazily and is cached once per worker; rendering/inference is serialized within a worker and resources are closed after each page. Sparse-page OCR failure is actionable; entirely unreadable files are rejected. Extraction runs off the event loop but remains a synchronous upload operation, with no background queue or hard per-document execution deadline. OCR wheels/models have a substantial download, memory and CPU footprint; first inference is slower. Complex columns, mathematical notation, handwriting and unsupported languages may extract poorly. Pixel/page limits are not a complete hostile-PDF sandbox.

## Docker Compose

Configure the ignored repository-root environment file used by [docker-compose.yml](docker-compose.yml), including PostgreSQL connection credentials, session secret and optional AI keys. Do not print or commit it. Compose maps the API to **8010** (container 8000), unlike local development on 8001.

```powershell
docker compose up --build
```

[backend/Dockerfile](backend/Dockerfile) installs Linux OpenCV runtime libraries and runs Alembic before Uvicorn. Compose provides PostgreSQL, Redis and MinIO as well as the API/frontend. Startup upgrades require the database to be reachable. For production, run migrations once in a controlled deployment step and review container dependency/security scans; this development image is not a security-hardened deployment.

## Backend verification

From the backend directory in the configured environment:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests alembic
..\.venv\Scripts\python.exe -m pip check
```

Tests use temporary SQLite databases/uploads, mocked LLM responses, generated PDF fixtures and a real OCR smoke test. They never use the configured application database or AI credentials. Fresh, unversioned legacy, baseline-stamped and already-hashed schemas are covered. PostgreSQL smoke tests skip unless `EDUTOOL_TEST_POSTGRES_URL` points to an operator-provided test service with schema-creation permission. Each creates/drops only a UUID-named test schema; never point it at production.

Frontend design/scrolling, keyboard behavior, browser end-to-end checks, production provider quality evaluation, persistent quiz analytics, cross-document chat and background OCR jobs are separate verification or implementation scope.
