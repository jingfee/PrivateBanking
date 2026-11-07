#!/usr/bin/env bash
# Start backend (auto-reload) and frontend (Vite) for local development.
#   ./dev.sh            start, seeding demo data the first time
#   ./dev.sh --reset    throw away the local database and seed it again
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD

for cmd in uv npm; do
  command -v "$cmd" >/dev/null || { echo "Saknar $cmd. Installera uv (https://docs.astral.sh/uv/) och Node.js 22." >&2; exit 1; }
done

if [ -f .env.dev ]; then set -a; source .env.dev; set +a; fi
export DATABASE_PATH="$(realpath -m "${DATABASE_PATH:-backend/data/dev.db}")"
export SCHEDULER_ENABLED="${SCHEDULER_ENABLED:-false}"
export EB_REDIRECT_URL="${EB_REDIRECT_URL:-http://localhost:5173/callback}"
export EB_KEY_PATH="$(realpath -m "${EB_KEY_PATH:-secrets/eb-sandbox.pem}")"

(cd backend && uv sync --quiet)
[ -d frontend/node_modules ] || (cd frontend && npm install)

if [ "${1:-}" = "--reset" ]; then rm -f "$DATABASE_PATH" "$DATABASE_PATH"-*; fi
if [ ! -f "$DATABASE_PATH" ]; then (cd backend && uv run python -m scripts.seed_demo "$DATABASE_PATH"); fi

trap 'kill 0' EXIT
(cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000) &
(cd frontend && npm run dev -- --port 5173 --strictPort) &
echo
echo "  App:      http://localhost:5173"
echo "  Databas:  $DATABASE_PATH"
echo
wait
