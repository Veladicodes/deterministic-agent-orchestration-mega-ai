# Deployment Guide

This document describes how to deploy the backend (API + worker + Postgres + Redis) and the frontend as a public demo. **No deployment has been performed as part of this repository's history** — deploying requires creating accounts on a hosting provider and entering billing/API-key secrets that only the project owner should hold. This guide gives exact, testable steps to do it yourself; it is not a substitute for having actually done it.

## Topology

```
┌─────────────────┐       ┌──────────────────────────┐
│  Vercel/Netlify  │──────▶│  Railway/Render (Docker)  │
│  frontend/ (SPA) │  CORS │  api service (FastAPI)    │
└─────────────────┘       │  worker service (Celery)  │
                           │  Postgres (managed)       │
                           │  Redis (managed)          │
                           └──────────────────────────┘
```

The API and worker both build from the repo's existing `Dockerfile`; nothing new needs to be built for deployment. `docker-compose.yml` remains the source of truth for local development and for the environment variables each service needs.

## 1. Backend (Railway or Render)

Both providers can build directly from this repo's `Dockerfile` and provision managed Postgres/Redis add-ons with a few clicks; steps are equivalent, described generically below.

1. Create a new project from this GitHub repo.
2. Add a **Postgres** and a **Redis** managed resource to the project; the provider will give you connection URLs.
3. Create the **api** service:
   - Build: Dockerfile at repo root.
   - Start command: already set by the `Dockerfile`'s `CMD` (`uvicorn api.main:app --host 0.0.0.0 --port 8000`); override the port if the provider requires binding to `$PORT`.
   - Environment variables (see `.env.example` for the full list):
     - `DATABASE_URL` — from the provider's Postgres add-on (must start with `postgresql+asyncpg://` — providers commonly hand back a plain `postgresql://` URL, which needs the `+asyncpg` driver segment added).
     - `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` — from the Redis add-on.
     - `CORS_ALLOWED_ORIGINS` — the deployed frontend's origin (e.g. `https://your-app.vercel.app`), comma-separated if more than one.
     - `USE_REAL_BACKENDS` — leave `false` (the default) for the public demo; see "Cost controls" below before ever setting this to `true` on a public deployment.
     - `QUERY_RATE_LIMIT_PER_DAY` — per-IP daily cap on `/query/run` and `/query/stream` (default 50; see `api/middleware/rate_limit.py`).
4. Create the **worker** service the same way, with the same environment variables, but with the start command `celery -A worker.celery_app.celery_app worker --loglevel=info` (as in `docker-compose.yml`).
5. After the api service is live, run migrations once: `alembic upgrade head` (as a one-off command/job in the provider's UI, using the same `DATABASE_URL`).
6. Verify: `curl https://<your-api-domain>/api/v1/health` should return `{"api": "ok", "db": "ok", "redis": "ok"}`.

## 2. Frontend (Vercel or Netlify)

1. Import the repo, set the project root to `frontend/`.
2. Build command: `npm run build` (already verified locally — see below). Output directory: `dist`.
3. Environment variable: `VITE_API_BASE_URL=https://<your-api-domain>/api/v1`.
4. Deploy. Verify the deployed page loads and that `Run` against a query returns a result (open the browser devtools network tab and confirm the CORS preflight to `/query/run` succeeds — if it doesn't, double check `CORS_ALLOWED_ORIGINS` on the api service matches the frontend's exact deployed origin).

**Local build verification already performed in this repo**: `cd frontend && npm run build` succeeds (`tsc -b && vite build`, ~230KB gzipped to ~72KB) and `npm run dev` was smoke-tested end-to-end against a locally running API — see the git history for this session's verification steps. Deploying the same build to Vercel/Netlify is a mechanical step from there, not something that changes the code.

## 3. Cost controls for a public demo

Real backends (`USE_REAL_BACKENDS=true`) call paid third-party APIs (Tavily, Anthropic) per query. Before ever enabling this on a publicly reachable deployment:

- Keep `USE_REAL_BACKENDS=false` (the default) unless you intend to pay for public traffic.
- `DailyRateLimitMiddleware` (`api/middleware/rate_limit.py`) caps `/query/run` and `/query/stream` to `QUERY_RATE_LIMIT_PER_DAY` requests per IP per day (in-memory, resets at UTC midnight) — set a conservative value (e.g. 10-20) before enabling real backends publicly. This is a single-instance guard, not a distributed rate limiter; it is not a substitute for actually reviewing your provider's billing alerts.
- Consider gating `USE_REAL_BACKENDS` behind a separate, non-public "demo" deployment with its own restricted API keys, rather than enabling it on the main public URL.

## 4. Reproducing this locally first

Before deploying, always verify locally (these exact commands were run against this repo as part of building the feature, not merely described):

```bash
docker compose up -d --build
# or, without Docker:
export DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 \
       CELERY_BROKER_URL=redis://localhost:6379/0 CELERY_RESULT_BACKEND=redis://localhost:6379/1
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 &
curl -X POST http://127.0.0.1:8000/api/v1/query/run -H "Content-Type: application/json" -d '{"query":"What is machine learning?"}'

cd frontend
cp .env.example .env   # VITE_API_BASE_URL defaults to http://localhost:8000/api/v1
npm install && npm run dev
```

## What's NOT set up

- No CI/CD pipeline auto-deploys on push (see README's "Roadmap" section — a basic GitHub Actions test workflow is a good next step, deployment automation beyond that is future work).
- No custom domain, TLS, or CDN configuration beyond what the hosting providers give by default.
- `worker/` (Celery) is not currently invoked by any code path in this repo (no task producer wired up yet) — it's deployed for completeness with `docker-compose.yml`'s existing topology, not because the live query path depends on it today.
