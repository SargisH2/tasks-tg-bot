set -eu

mkdir -p /tmp/voice
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
