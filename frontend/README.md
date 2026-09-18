# Frontend

React + Vite + TypeScript + Tailwind demo UI for the deterministic agent orchestration backend.

- **Run tab**: submits a query, shows each pipeline stage live via SSE, then the final answer with provenance links and `execution_hash`.
- **Replay/diff tab**: runs the same query twice and compares the two execution traces via `/api/v1/replay/compare` — the concrete evidence that the orchestration layer is deterministic and reproducible.

## Local development

```bash
cp .env.example .env   # VITE_API_BASE_URL defaults to http://localhost:8000/api/v1
npm install
npm run dev             # requires the backend API running locally
```

## Build

```bash
npm run build            # type-checks (tsc -b) then builds to dist/
```

See the repo root's [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) for deploying this alongside the backend.
