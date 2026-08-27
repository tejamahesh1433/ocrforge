#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

source .venv/bin/activate

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://ocrforge:ocrforge_dev@localhost:5435/ocrforge}"

cd backend

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8001
