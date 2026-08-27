# AI-Powered Multi-Cloud File Intelligence Platform — Backend

Phases 1–3 are complete.

- **Phase 1** — FastAPI skeleton, config, PostgreSQL + SQLAlchemy models, logging, health check
- **Phase 2** — JWT auth, Google Drive OAuth connector, S3-compatible storage connector
  (Backblaze B2 free tier / AWS S3 / MinIO), file listing / download / upload / import,
  file-metadata persistence
- **Phase 3** — Document processing pipeline: PDF / DOCX / TXT / CSV text extraction,
  OCR (Tesseract), table extraction (pdfplumber), token-aware chunking with overlap,
  per-stage job tracking

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (SQLite also works for quick local demos / tests)
- A Google Cloud project (for Drive) — free
- A Backblaze B2 account (for S3-compatible storage) — 10 GB free, no credit card
- **OCR (optional but recommended):** system packages `tesseract-ocr` + `poppler-utils`
  ```bash
  # Debian/Ubuntu
  sudo apt install tesseract-ocr poppler-utils
  # macOS
  brew install tesseract poppler
  # Windows — installers: https://github.com/UB-Mannheim/tesseract/wiki and poppler-windows
  ```
  Without them, text-based documents still process normally; OCR is only needed for
  scanned PDFs and images (the API returns a clear error telling you to install Tesseract).

---

## Quick Start

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in at minimum:
#   SECRET_KEY  — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
#   DATABASE_URL — your local PostgreSQL connection string
```

> For a zero-dependency demo you can also use SQLite:
> `DATABASE_URL=sqlite:///./dev.db`

### 4. Create the PostgreSQL database (skip if using SQLite)

```bash
psql -U postgres -c "CREATE DATABASE file_intelligence;"
```

### 5. Run database migrations

```bash
alembic upgrade head
```

> On first run, tables are also auto-created via SQLAlchemy on startup.

### 6. Start the development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Verify the setup

| Check                | URL                                          |
| -------------------- | -------------------------------------------- |
| Health check         | http://localhost:8000/api/v1/health          |
| Interactive API docs | http://localhost:8000/docs (DEBUG=true only) |

Expected health response:
```json
{
  "status": "ok",
  "app": "AI File Intelligence Platform",
  "environment": "development",
  "database": "ok"
}
```

---

## Phase 2 — Using the API

### 1. Create an account and log in

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "password": "supersecret123"}'

# Log in → returns a JWT
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "supersecret123"}'

# Use the token
curl http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer <ACCESS_TOKEN>"
```

All cloud/file/document endpoints require the `Authorization: Bearer <token>` header.
Passwords are bcrypt-hashed; cloud credentials are encrypted at rest (Fernet, key
derived from `SECRET_KEY`) before being stored in `connected_cloud_accounts`.

### 2. Connect Google Drive (OAuth 2.0 user flow)

```bash
curl http://localhost:8000/api/v1/cloud/google/connect -H "Authorization: Bearer <TOKEN>"
# → {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?..."}

# Open authorization_url in a browser, sign in and grant access.
# Google redirects to /api/v1/cloud/google/callback which stores the tokens:
# → {"status": "connected", "provider": "google_drive", "account": "you@gmail.com"}

curl http://localhost:8000/api/v1/cloud/google/status -H "Authorization: Bearer <TOKEN>"
```

Access tokens are refreshed automatically with the stored refresh token.
Scopes requested (least privilege): `drive.readonly` (browse/read everything),
`drive.file` (files the app creates), `userinfo.email`.

### 3. Connect S3-compatible storage (Backblaze B2 — free 10 GB)

```bash
curl -X POST http://localhost:8000/api/v1/cloud/s3/connect \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{
        "access_key_id": "<B2 keyID>",
        "secret_access_key": "<B2 application key>",
        "region": "us-west-004",
        "endpoint_url": "https://s3.us-west-004.backblazeb2.com",
        "bucket_name": "<your-bucket>"
      }'
```

Credentials are validated against the bucket before being stored. If the request
body is empty, the server falls back to the `S3_*` environment variables — so you
can also configure the bucket once in `.env` and skip the connect call entirely.
Leave `S3_ENDPOINT_URL` empty to talk to real AWS S3 instead of B2 (same code path).

### 4. List, download, upload and import files

```bash
# List files live from a provider (folder_id = Drive folder ID or S3 prefix)
curl "http://localhost:8000/api/v1/files?provider=google_drive" -H "Authorization: Bearer <TOKEN>"
curl "http://localhost:8000/api/v1/files?provider=s3&folder_id=reports/" -H "Authorization: Bearer <TOKEN>"

# Download a file
curl -OJ "http://localhost:8000/api/v1/files/<FILE_ID>/download?provider=google_drive" \
  -H "Authorization: Bearer <TOKEN>"

# Upload a local file (creates a Document with SHA-256 dedup hash)
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer <TOKEN>" \
  -F "provider=s3" -F "file=@./report.pdf"

# Import (track) an existing cloud file into the platform
curl -X POST "http://localhost:8000/api/v1/files/<FILE_ID>/import?provider=google_drive" \
  -H "Authorization: Bearer <TOKEN>"

# Browse tracked document metadata
curl "http://localhost:8000/api/v1/documents" -H "Authorization: Bearer <TOKEN>"
curl "http://localhost:8000/api/v1/documents/<DOC_ID>/status" -H "Authorization: Bearer <TOKEN>"
```

Google Docs/Sheets/Slides are exported automatically (Docs → PDF, Sheets → CSV)
when downloaded. Uploads are validated against `ALLOWED_EXTENSIONS` and
`MAX_FILE_SIZE_MB`.

---

## Phase 3 — Processing documents

Turn a tracked file into searchable chunks:

```bash
# Trigger the pipeline (runs in the background)
curl -X POST "http://localhost:8000/api/v1/documents/<DOC_ID>/process" \
  -H "Authorization: Bearer <TOKEN>"
# → 202 {"status": "processing", ...}
# (equivalent provider-file alias: POST /api/v1/files/<FILE_ID>/process?provider=s3)

# Poll progress — per-stage job details included
curl "http://localhost:8000/api/v1/documents/<DOC_ID>/status" -H "Authorization: Bearer <TOKEN>"

# Inspect the results
curl "http://localhost:8000/api/v1/documents/<DOC_ID>/chunks" -H "Authorization: Bearer <TOKEN>"
curl "http://localhost:8000/api/v1/documents/<DOC_ID>/tables" -H "Authorization: Bearer <TOKEN>"
```

### Pipeline stages

| Stage            | What happens                                                                                                                                                   |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Download         | File bytes fetched from Drive/B2 and cached under `LOCAL_STORAGE_PATH/<doc_id>/`                                                                               |
| Text extraction  | `pypdf` (per page), `python-docx` (paragraphs + tables), TXT (utf-8/latin-1), CSV (pandas → `column: value` lines)                                             |
| OCR              | Images always; PDF pages with no extracted text are OCRed page-by-page (poppler rasterize → Tesseract)                                                         |
| Table extraction | `pdfplumber` for PDFs; CSVs stored as a native table                                                                                                           |
| Chunking         | Token-aware chunks (`CHUNK_SIZE_TOKENS=800`, `CHUNK_OVERLAP_TOKENS=120`) with page numbers preserved; tiktoken when available, offline-safe estimate otherwise |

Every stage is recorded in `processing_jobs` (type, status, error, timings) — visible in
the status endpoint. Reprocessing is safe: chunks, tables and jobs are replaced.
A scanned file without Tesseract installed fails with an actionable error instead of
silently producing empty text.

---

## Run tests

```bash
pytest tests/ -v
```

The suite runs on SQLite in-memory (no PostgreSQL needed) and mocks the external
cloud APIs — 88 tests cover auth, both connectors, the files API, metadata persistence
and the full processing pipeline. The two real-OCR tests are skipped automatically
when Tesseract isn't installed on the machine running the tests.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, lifespan
│   ├── api/
│   │   ├── deps.py              # get_current_user (JWT)
│   │   └── v1/
│   │       ├── router.py        # Wires all endpoint routers
│   │       └── endpoints/
│   │           ├── auth.py      # register / login / me          (Phase 2)
│   │           ├── health.py
│   │           ├── cloud_google.py  # OAuth connect/callback/status (Phase 2)
│   │           ├── cloud_s3.py      # S3-compatible connect/status  (Phase 2)
│   │           ├── files.py     # list/download/upload/import     (Phase 2)
│   │           ├── documents.py # metadata + process/chunks/tables (Phases 2-3)
│   │           ├── ai.py        # search/chat stubs               (Phases 4-5)
│   │           └── reports.py   # report generation stub          (Phase 6)
│   ├── config/settings.py       # All config via environment variables
│   ├── models/models.py         # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/
│   │   ├── registry.py          # provider → service factory
│   │   ├── google_drive/        # OAuth helpers + Drive operations
│   │   ├── s3_storage/          # boto3 S3-compatible operations
│   │   ├── document_processing/ # extractors, chunking, pipeline   (Phase 3)
│   │   ├── ocr/                 # Tesseract wrapper                (Phase 3)
│   │   └── table_extraction/    # pdfplumber wrapper               (Phase 3)
│   ├── database/session.py      # DB engine, session, Base
│   └── utils/
│       ├── logger.py            # Structured logging
│       └── security.py          # bcrypt, JWT, Fernet encryption
├── alembic/                     # Database migrations
├── tests/                       # 37 tests (SQLite + mocks)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Environment Variables

| Variable               | Description                               | Required Now |
| ---------------------- | ----------------------------------------- | ------------ |
| `SECRET_KEY`           | JWT signing + credential-encryption key   | Yes          |
| `DATABASE_URL`         | PostgreSQL (or SQLite) connection string  | Yes          |
| `GOOGLE_CLIENT_ID`     | Google OAuth client ID                    | For Drive    |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret                | For Drive    |
| `GOOGLE_REDIRECT_URI`  | OAuth callback URL                        | No (default) |
| `S3_ACCESS_KEY_ID`     | S3/B2 access key (keyID for B2)           | For S3/B2    |
| `S3_SECRET_ACCESS_KEY` | S3/B2 secret key                          | For S3/B2    |
| `S3_REGION`            | Storage region                            | No           |
| `S3_BUCKET_NAME`       | Bucket name                               | For S3/B2    |
| `S3_ENDPOINT_URL`      | Empty = AWS S3; B2 endpoint for Backblaze | For B2       |
| `LOCAL_STORAGE_PATH`   | Local cache for downloaded files          | No           |
| `CHUNK_SIZE_TOKENS`    | Target size for generated chunks          | No           |
| `CHUNK_OVERLAP_TOKENS` | Overlap between consecutive chunks        | No           |
| `OCR_MAX_PAGES`        | Maximum PDF pages processed by OCR        | No           |
| `OPENAI_API_KEY`       | OpenAI API key                            | Phase 4      |
| `QDRANT_URL`           | Qdrant vector DB URL                      | Phase 4      |

---

## Cloud Infrastructure Setup

### Google Cloud (free)

1. Go to https://console.cloud.google.com and create a project
2. Enable the **Google Drive API**
3. Configure the OAuth consent screen (External; add yourself as a Test user)

### Backblaze B2 (free 10 GB, no credit card)

1. Create an account at https://www.backblaze.com/cloud-storage
2. B2 Cloud Storage → **Create Bucket** (Private)
3. App Keys → **Add a New Application Key** restricted to that bucket
   (read/write — the least-privilege equivalent of the original AWS policy)
4. Fill `.env` (or the `/cloud/s3/connect` request) with the keyID, key, bucket
   name and the bucket's S3 endpoint, e.g. `https://s3.us-west-004.backblazeb2.com`

### AWS S3 (optional — the same connector also speaks to real AWS)

1. Create an IAM user with only `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`,
   `s3:ListBucket` on one bucket
2. Leave `S3_ENDPOINT_URL` empty and fill the other `S3_*` variables

---

## Next Step — Phase 4

Embeddings & vector search: generate embeddings for the stored chunks
(OpenAI `text-embedding-3-small`), configure Qdrant, store vectors with metadata,
and implement similarity search with metadata filtering.
