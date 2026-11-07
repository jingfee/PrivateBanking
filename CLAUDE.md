# PrivateBanking

Private, self-hosted app that fetches the owner's own bank and card transactions via
Enable Banking (PSD2, read-only) and stores them in SQLite. UI text is Swedish.

## Layout
- `backend/` – FastAPI + SQLAlchemy 2 + Alembic, Python 3.13, managed with `uv`
  - `app/enablebanking.py` API client (JWT RS256, `kid` = app id), `app/normalize.py` raw → stored fields,
    `app/sync.py` fetch/upsert, `app/api.py` routes, `app/main.py` app factory + scheduler + SPA serving
- `frontend/` – SvelteKit 2 / Svelte 5 (runes), adapter-static SPA, served by the backend in production
- `Dockerfile` (one image), `docker-compose.yml` (runs `ghcr.io/jingfee/privatebanking`), `.github/workflows/ci.yml`

## Commands
- Run locally: `./dev.sh` (backend :8000 with reload, Vite :5173 proxying `/api` and `/callback`;
  seeds demo data into `backend/data/dev.db` on first run; `./dev.sh --reset` to reseed)
- Backend tests: `cd backend && uv run pytest -q`
- Frontend checks: `cd frontend && npm run check && npm run build`
- New migration after changing `app/models.py`: `cd backend && uv run alembic revision --autogenerate -m "..."`
  (migrations run automatically on startup; the DB is backed up to `data/backups/` first)

## Rules
- Amounts are stored as signed integer öre (`amount_ore`, negative = money out). Never floats.
- Never hold a database transaction open while calling Enable Banking (see `sync.py`).
- PSD2 allows ~4 unattended fetches per day per account: don't add extra syncs casually,
  and never sync against real banks from local development (use the sandbox app).
- Never commit `.env*`, `secrets/`, `*.pem` or `data/`.
- Work on a branch and open a PR; CI must pass before merging to `main`. Merging to `main` builds and
  pushes the image that deployments pull.
