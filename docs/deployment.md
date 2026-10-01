# Deployment Preparation

No external account or deployment is performed by this project.

## Local containers

With Docker Desktop running:

```powershell
docker compose up --build
```

- Dashboard: `http://localhost:8080`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`

The frontend Nginx container proxies `/api` to the backend. SQLite is mounted on
the `ringguard-data` named volume. Stop with `docker compose down`; add `-v` only
when you intentionally want to delete persisted investigator actions.

## Separate hosting

Backend requirements:

- Python 3.14
- command: `uvicorn backend.api.app:app --host 0.0.0.0 --port 8000`
- writable persistent path for `RINGGUARD_DB_PATH`
- health check: `GET /health`
- set `RINGGUARD_CORS_ORIGINS` to the exact frontend origins

Frontend requirements:

- Node 22 and pnpm 11.19
- build command: `pnpm install --frozen-lockfile && pnpm run build`
- publish directory: `frontend/dist`
- build variable: `VITE_API_URL=https://your-backend.example`
- SPA fallback: unknown paths return `index.html`

Before public exposure, add authentication, RBAC, TLS, rate limiting, managed
secrets, centralized logs, a shared database, and multi-worker-safe state.
