# AI-Powered Multi-Cloud File Intelligence Platform — Backend

Phases 1–5 are complete.

- **Phase 1** — FastAPI skeleton, config, PostgreSQL + SQLAlchemy models, logging, health check
- **Phase 2** — JWT auth, Google Drive OAuth connector, S3-compatible storage connector
  (Backblaze B2 free tier / AWS S3 / MinIO), file listing / download / upload / import,
  file-metadata persistence
- **Phase 3** — Document processing pipeline: PDF / DOCX / TXT / CSV text extraction,
  OCR (Tesseract), table extraction (pdfplumber), token-aware chunking with overlap,
  per-stage job tracking
- **Phase 4** — Embeddings & vector search: **Jina AI** embeddings (`jina-embeddings-v3`)
  stored in **Qdrant**, automatic embedding during processing, semantic search with
  metadata filtering and strict per-user isolation
- **Phase 5** — RAG: retrieval-augmented chat over the user's documents with the
  **NVIDIA hosted LLM** (`nvidia/nemotron-3.5-lightning-30b-a3b`), bounded
  injection-hardened context construction and application-side source attribution

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

**S3 connection states:**
- *Never connected* → the server's `S3_*` env credentials are used automatically
- *Connected* → your per-user credentials (encrypted at rest) are used
- *Disconnected* → S3 access is **fully blocked** until you reconnect; the env
  fallback deliberately does not apply after an explicit disconnect


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

## Phase 4 — Embeddings & semantic search (Jina AI + Qdrant)

**Architecture — two separate roles:**

| Role | Technology | Notes |
|---|---|---|
| Embedding generation | **Jina AI** (hosted embedding API) | `jina-embeddings-v3`, 1024 dimensions |
| Vector storage & search | **Qdrant** (vector database) | cosine similarity, metadata filtering |

There is **no OpenAI dependency** — Jina is reached over plain HTTP via the project's
existing `httpx` client (no SDK required).

### 1. Jina AI configuration

Get a free API key at https://jina.ai/ and set it in `.env`:

```env
JINA_API_KEY=your-free-jina-key
EMBEDDING_MODEL=jina-embeddings-v3
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=64
JINA_API_URL=https://api.jina.ai/v1/embeddings
```

A free Jina key is sufficient for development and testing (rate limits apply — it is
not unlimited). Document chunks are embedded with the `retrieval.passage` task and
search queries with `retrieval.query`, as recommended for retrieval-oriented models.

### 2. Qdrant configuration

```bash
# Option A — local Docker (free)
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
# → QDRANT_URL=http://localhost:6333

# Option B — Qdrant Cloud (free tier available)
# → QDRANT_URL=https://<your-cluster>.cloud.qdrant.io + QDRANT_API_KEY

# Option C — embedded in-memory mode (tests only, no persistence)
# → QDRANT_URL=:memory:
```

The collection is created automatically on first use: cosine distance, vector size =
`EMBEDDING_DIMENSIONS`, payload indexes on the filterable fields. The test suite uses
in-memory mode and never requires a running Qdrant server.

### 3. How embeddings are stored

Processing a document now ends with an embedding stage (when `JINA_API_KEY` is set):
chunk texts → Jina embeddings → Qdrant vectors. Qdrant payloads carry **metadata only**
(`user_id`, `document_id`, `chunk_id`, `chunk_index`, `page_number`, `source`,
`file_name`, `mime_type`) — chunk text stays in PostgreSQL and is hydrated when search
results are returned, so content is never duplicated in the vector store.

If the embedding stage fails, the document is marked **failed** with the error recorded
in its processing jobs — it never silently appears as successfully processed. Documents
processed without a Jina key simply skip the stage (Phase 3 behavior unchanged).

Backfill or retry embeddings for an already-processed document:

```bash
curl -X POST "http://localhost:8000/api/v1/documents/<DOC_ID>/embed" \
  -H "Authorization: Bearer <TOKEN>"
# → {"document_id": "...", "status": "completed", "chunks_embedded": 12, "model": "jina-embeddings-v3"}
```

The operation is retry-safe (existing vectors are replaced, never duplicated).

### 4. Semantic search

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"query": "quarterly revenue analysis", "limit": 5}'

# with metadata filters:
curl -X POST http://localhost:8000/api/v1/search \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"query": "revenue", "source": "s3", "mime_type": "application/pdf", "min_score": 0.3}'

# search within one document:
curl -X POST http://localhost:8000/api/v1/search \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"query": "revenue", "document_id": "<DOC_ID>"}'
```

Results are ranked by cosine similarity and include the matched chunk content,
score, page number and document metadata. **User isolation is mandatory**: every
search is scoped to the authenticated user's vectors — no user can ever retrieve
another user's results.

---

## Phase 5 — RAG chat (NVIDIA hosted LLM)

Ask questions about your own documents: the answer is generated **only** from your
retrieved chunks, with traceable sources.

### Architecture

```
User question
   → query processing (validation + normalization)
   → Jina query embedding (retrieval.query task)          [Phase 4]
   → Qdrant semantic retrieval (scoped to the user)       [Phase 4]
   → PostgreSQL chunk hydration (authoritative text)      [Phase 4]
   → bounded context construction (RAG_MAX_CONTEXT_CHUNKS / RAG_MAX_CONTEXT_CHARS)
   → NVIDIA hosted LLM (chat completions, thinking disabled)
   → answer + source attribution built by the application from retrieval results
```

The LLM never constructs citations — `sources` is built from the exact chunks
supplied in the context, so nothing can be invented. If nothing relevant is found,
the LLM is not called and a deterministic "couldn't find relevant information"
answer is returned with an empty source list.

### Prompt-injection handling

Retrieved document content (including OCR text and filenames) is treated as
**untrusted data**, never as instructions:

- every chunk is wrapped in `<document>...</document>` blocks in the context
- the system prompt separates **TRUSTED INSTRUCTIONS** from **UNTRUSTED DATA** and
  explicitly instructs the model to keep following application instructions when a
  document says things like "ignore previous instructions"
- document content cannot break out of its wrapper (closing tags inside content
  are neutralized) and metadata is flattened so it cannot forge context structure

This is a practical application-level defense, not a guarantee — prompt injection
cannot be eliminated entirely in this architecture.

### Configuration

```env
NVIDIA_API_KEY=            # key from https://build.nvidia.com/
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_TIMEOUT_SECONDS=30
RAG_MAX_CONTEXT_CHUNKS=8
RAG_MAX_CONTEXT_CHARS=24000
```

Both the Jina key (Phase 4 retrieval) and the NVIDIA key are required for chat.

### Using the chat API

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"message": "What is semantic search?"}'
```

Response:

```json
{
  "message": "What is semantic search?",
  "answer": "According to your notes, semantic search retrieves information based on meaning rather than exact keyword matching.",
  "sources": [
    {
      "document_id": "3f2b...",
      "chunk_id": "9a1c...",
      "filename": "phase34-test.txt",
      "page_number": 1,
      "score": 0.42
    }
  ]
}
```

Optional parameters: `"limit": 5` (1–20) and `"min_score": 0.2` (0–1) tune retrieval.
Retrieval is always scoped to the authenticated user. Errors: `401` unauthenticated,
`422` invalid input, `503` not configured, `502` upstream Jina/Qdrant/NVIDIA failures
(sanitized messages — no stack traces, keys or internal details).

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
| `JINA_API_KEY`         | Jina AI embedding key (free tier works)   | For Phase 4+ |
| `EMBEDDING_MODEL`      | Jina embedding model                      | No (default) |
| `EMBEDDING_DIMENSIONS` | Embedding vector size                     | No (default) |
| `QDRANT_URL`           | Qdrant vector DB URL (or `:memory:`)      | For Phase 4+ |
| `NVIDIA_API_KEY`       | NVIDIA hosted LLM API key                 | For Phase 5+ |
| `NVIDIA_MODEL`         | LLM model for RAG generation              | No (default) |
| `NVIDIA_TIMEOUT_SECONDS` | LLM request timeout (seconds)           | No (default) |
| `RAG_MAX_CONTEXT_CHUNKS` | Max chunks supplied to the LLM          | No (default) |
| `RAG_MAX_CONTEXT_CHARS` | Max characters of constructed context     | No (default) |

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

## Next Step — Phase 6

AI features: document summarization, report generation and multi-document
analysis — built on the Phase 4/5 retrieval and generation stack.
