# AI-Powered Multi-Cloud File Intelligence Platform — Backend

## Phase 1: Foundation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- (Optional for later phases) Docker, Qdrant, Tesseract OCR

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

### 4. Create the PostgreSQL database

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

| Check | URL |
|---|---|
| Health check | http://localhost:8000/api/v1/health |
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

## Run tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, lifespan
│   ├── config/
│   │   └── settings.py          # All config via environment variables
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # Wires all endpoint routers
│   │       └── endpoints/
│   │           ├── health.py
│   │           ├── cloud_google.py
│   │           ├── cloud_aws.py
│   │           ├── files.py
│   │           ├── ai.py
│   │           ├── documents.py
│   │           └── reports.py
│   ├── models/
│   │   └── models.py            # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request/response schemas (Phase 2+)
│   ├── services/                # Business logic modules (Phase 2+)
│   ├── database/
│   │   └── session.py           # DB engine, session, Base
│   └── utils/
│       └── logger.py            # Structured logging
├── alembic/                     # Database migrations
├── tests/
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Environment Variables Required

| Variable | Description | Required Now |
|---|---|---|
| `SECRET_KEY` | JWT signing key | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Phase 2 |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | Phase 2 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service account JSON | Phase 2 |
| `AWS_ACCESS_KEY_ID` | IAM user access key | Phase 2 |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Phase 2 |
| `AWS_S3_BUCKET_NAME` | S3 bucket name | Phase 2 |
| `OPENAI_API_KEY` | OpenAI API key | Phase 4 |
| `QDRANT_URL` | Qdrant vector DB URL | Phase 4 |

---

## Cloud Infrastructure — Manual Setup Required

### Google Cloud

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. `file-intelligence-platform`)
3. Enable APIs: **Google Drive API**, **Cloud Resource Manager API**
4. Create OAuth 2.0 credentials → Web Application
   - Authorized redirect URI: `http://localhost:8000/api/v1/cloud/google/callback`
5. Create a Service Account with role: **Viewer** (least privilege)
6. Download the service account JSON key → store path in `GOOGLE_SERVICE_ACCOUNT_JSON`
7. Store `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`

### AWS

1. Log in to https://console.aws.amazon.com (do NOT use root credentials)
2. Create an IAM user (e.g. `file-intelligence-app`)
3. Attach a custom policy with ONLY:
   ```json
   {
     "Effect": "Allow",
     "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
     "Resource": ["arn:aws:s3:::YOUR_BUCKET_NAME", "arn:aws:s3:::YOUR_BUCKET_NAME/*"]
   }
   ```
4. Create an S3 bucket in your preferred region
5. Enable bucket versioning and server-side encryption (SSE-S3)
6. Store access key and secret in `.env`

---

## Next Step — Phase 2

Implement Google Drive and AWS S3 connectors:
- OAuth flow for Google Drive
- File listing and downloading
- S3 file listing and downloading
- Store file metadata in the `documents` table
