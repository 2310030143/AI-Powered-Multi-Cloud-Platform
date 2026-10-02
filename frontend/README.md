# File Intelligence — Frontend

React + TypeScript + Vite dashboard for the AI-Powered Multi-Cloud File
Intelligence Platform backend (Phases 1–6 APIs).

## Requirements

- Node.js 18+ (LTS recommended)
- The FastAPI backend running locally (see `../backend/README.md`)

## Installation

```bash
cd frontend
npm install
```

## Environment configuration

Copy the example and adjust if needed:

```bash
cp .env.example .env.local
```

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | Backend base URL. The relative default is served through the Vite dev proxy (no CORS setup needed). For a deployed frontend, set the absolute backend URL, e.g. `http://localhost:8000/api/v1`. |

No secrets belong in the frontend — it only ever knows the backend URL.
All provider credentials (Jina, NVIDIA, Ollama, S3, Google) stay on the backend.

## Development

```bash
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` → `http://localhost:8000`, so start the backend
first. The backend also allows `http://localhost:5173` in its CORS defaults.

## Production build

```bash
npm run build        # type-checks, then bundles to dist/
npm run preview      # serve the production build locally
```

Deploy `dist/` behind any static host, with `VITE_API_BASE_URL` pointing at
the deployed backend when you build.

## Tests & type checking

```bash
npm test             # Vitest + React Testing Library
npm run typecheck    # tsc --noEmit
```

## Feature map

| Page | Backend APIs used |
|---|---|
| Login / Register | `POST /auth/login`, `POST /auth/register`, `GET /auth/me` |
| Dashboard | `GET /documents`, `GET /cloud/{google,s3}/status` |
| Cloud Connections | `GET /cloud/google/connect`, `{status,disconnect}`, `POST /cloud/s3/connect` |
| Documents (browse, upload, cloud import) | `GET/POST /documents`, `/files`, `/files/upload`, `/files/{id}/import` |
| Document detail (process, chunks, tables, summarize, download) | `/documents/{id}` actions, `/files/{id}/download` |
| Semantic Search | `POST /search` |
| AI Chat | `POST /chat` |
| Multi-Document Analysis | `POST /analysis/multi-document` |
| Reports | `POST /reports/generate` |
