# Data Nucleus Knowledge Hub

This project provides a small RAG (Retrieval Augmented Generation) application with a FastAPI backend and a Vite/React front‑end. The two services communicate over HTTP and use bearer tokens for authentication. The front‑end includes a `/profile` page that shows the logged in user's information and allows logging out. Admins can manage collections and users via pages under `/admin`.

## Features
- **Polished admin UI** – reusable `AdminCard` components and flex‑wrapped action buttons keep layouts consistent and prevent overlap on small screens.
- **Pluggable embeddings & hybrid retrieval** – embeddings are cached in SQLite and can be served by OpenAI or local SentenceTransformers; search fuses vector and optional BM25 results, then re‑ranks with a cross‑encoder before MMR.
- **Domain switching** – set a single `APP_DOMAIN` environment variable to load industry‑specific prompts, guardrails, retrieval defaults, citation styles, and tool settings.

## Prerequisites

- Node.js and npm
- Python 3.10+

## Setup

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in the required values (see [Environment variables](#environment-variables)).
3. Install backend dependencies inside a virtual environment:
   ```sh
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Initialize the database and seed the default admin user:
   ```sh
   mkdir -p data/raw data/chroma logs
   python -m scripts.seed_admin
   ```
   The seeded credentials are `admin@admin.com` / `Admin#123456`.
5. Install frontend dependencies:
   ```sh
   npm install
   ```

## Environment variables

| Variable | Description |
| --- | --- |
| `OPENAI_API_KEY` | API key for OpenAI models |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | choose text embedding backend |
| `EMBEDDING_CACHE_DB` | path to the SQLite cache for embeddings |
| `USE_BM25` / `BM25_INDEX_DIR` | toggle and storage location for optional BM25 index |
| `USE_RERANKER` / `RERANKER_MODEL` | enable cross‑encoder re‑ranking and specify the model |
| `VITE_API_BASE_URL` | backend URL used by the frontend |
| `ALLOWED_ORIGINS` | comma‑separated origins allowed for CORS |
| `JWT_SECRET` | secret used to sign access tokens |
| `ALLOWED_ORIGIN_REGEX` | optional regex to match additional origins |
| `SQLALCHEMY_DATABASE_URI` | database connection string |
| `CHROMA_PERSIST_DIR` | directory for Chroma vector store persistence |
| `RAW_DOCS_DIR` | location for uploaded raw documents |
| `MAX_UPLOAD_MB` | maximum upload size in megabytes |
| `TOP_K` | number of retrieval candidates to consider |
| `MMR_LAMBDA` | lambda parameter for MMR diversification |
| `ANSWER_TEMPERATURE` | temperature for answer generation |
| `APP_DOMAIN` | select domain-specific prompts, guardrails, retrieval defaults, citation styles, and tool settings (`manufacturing`, `healthcare`, `finance`, `hospitality`, or `legal`) |

## Running the app

### Backend

Start the FastAPI server:
```sh
uvicorn api.main:app --reload
```
The API will be available at `http://localhost:8000`.

### Frontend

Run the Vite development server:
```sh
npm run dev
```
Visit `http://localhost:5173` in your browser. After logging in you can access your account details at `/profile`. Admin users can browse `/admin/users` and `/admin/collections` to manage data.

The login endpoint accepts a JSON body containing `email` and `password`.

## Testing

To run code quality checks and tests:
```sh
npm run lint
pytest
```


## Quickstart (Windows/Mac/Linux)

### 1) Backend (FastAPI)
```bash
# from repo root (use your venv)
copy .env.example .env            # or: cp .env.example .env
# set at minimum:
#  - OPENAI_API_KEY=sk-...
#  - JWT_SECRET=change-me
#  - (optional) ALLOWED_ORIGINS includes http://localhost:8080 and http://127.0.0.1:8080

mkdir data\raw data\chroma logs # (Windows)  OR  mkdir -p data/raw data/chroma logs
python -m scripts.seed_admin
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### 2) Frontend (Vite/React)
```bash
# repo root
npm install
# ensure .env has: VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev   # opens at http://localhost:8080
```

### Default admin
- **Email:** `admin@admin.com`
- **Password:** `Admin#123456`

> If login fails with “Failed to fetch”, confirm:
> - backend is listening at `127.0.0.1:8000`
> - your `.env` has `ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080`
> - your frontend `.env` has `VITE_API_BASE_URL=http://127.0.0.1:8000`
```

### Index documents
Go to **Admin → Collections**, create a collection, upload a small PDF, wait for status `indexed`, then start chatting.


## Troubleshooting
- **Login shows `Failed to fetch`**: your browser origin might be a LAN IP (e.g. `http://192.168.x.x:8080`). Add that origin to `.env` `ALLOWED_ORIGINS` or set `ALLOWED_ORIGIN_REGEX` to match it, restart the backend.
- **Admin pages blank**: open DevTools → Network, verify requests to `/api/admin/...` are `200`. If `401`, ensure the token is present; if `CORS` blocked, see above.
