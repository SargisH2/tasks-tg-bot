# Omni-Channel Task Management System

A production-ready full-stack **Omni-Channel Task Management System** built with **FastAPI**, **PostgreSQL 16 (SQLAlchemy 2.0 + Alembic)**, **aiogram 3.x (Webhook Mode)**, **Celery 5 + Redis 7**, **OpenAI Whisper & Structured Outputs (`gpt-4o-mini`)**, **Caddy 2 Automatic HTTPS**, and a **React 18 + TypeScript + `@dnd-kit` Drag-and-Drop Kanban Dashboard**.

---

## Key Capabilities

1. **Telegram Authentication, Mini App & Dev Login Helper**:
   - Verifies Telegram Login Widget payloads using `HMAC-SHA256` against `SHA256(TELEGRAM_BOT_TOKEN)` and issues signed `HTTPBearer` JWT tokens.
   - Embeds a **`[📱 Open Kanban Board]`** Telegram Mini App (`WebAppInfo`) button directly inside Telegram messages when an HTTPS webhook URL is configured.
   - Includes a local Dev Login mode (`ALLOW_DEV_AUTH=true` / `VITE_ALLOW_DEV_AUTH=true`) for development, disabled (`false`) by default in production (`docker-compose.prod.yml`).
2. **Omni-Channel Task Creation & Hands-Free Voice Commands**:
   - **Text Messages**: Immediately creates a `PRIVATE` task, preserves `telegram_message_id` and `telegram_chat_id`, extracts `@username` mentions (`@[a-zA-Z0-9_]{5,32}`), warns if any mentioned user is not registered yet, and replies with an interactive inline keyboard.
   - **Voice Notes (New Task)**: Downloads `/tmp/voice/{task_id}.ogg`, transcribes audio asynchronously via **OpenAI Whisper (`whisper-1`)**, extracts `@username` mentions from the transcript, cleans up the `.ogg` file inside a `finally` block, and updates both the web board and Telegram message in place.
   - **Voice Command Mode (Reply to Existing Task)**: Replying to any existing task card in Telegram with a voice note transcribes the instruction and uses `gpt-4o-mini` (`VoiceCommandResult`) to update status, priority, visibility, title/description, checkpoint completions, new checkpoints, and collaborators hands-free.
3. **Granular `@username` Access Control, User Directory & Availability Warnings**:
   - **`PRIVATE` Tasks**: Visible and editable exclusively by `task.owner_id == current_user.id`.
   - **`PUBLIC` Tasks**: Visible and editable by the task owner **and** any authenticated Telegram user whose normalized `@username` appears in `task_mentions`.
   - **Users Directory & Live Hints**: `GET /api/v1/users` and the Telegram `/users` command list all registered users, power live `@username` autocomplete hints in the web UI, and show a `"User not available (@username is not registered yet)"` warning whenever an unregistered handle is mentioned.
4. **Separate On-Demand AI Workflows**:
   - **`✨ AI Improve Task`** (`POST /api/v1/tasks/{id}/improve` or Telegram callback `ai_improve:{id}`): Uses OpenAI `gpt-4o-mini` Structured Outputs (`ImprovedTaskResult`) to refine the task title and description, infer task priority (`LOW`, `MEDIUM`, `HIGH`, `URGENT`), and extract domain tags.
   - **`☑️ Generate Checkpoints`** (`POST /api/v1/tasks/{id}/checkpoints/generate` or Telegram callback `ai_checkpoints:{id}`): Uses OpenAI `gpt-4o-mini` Structured Outputs (`GeneratedCheckpointsResult`) to decompose the task into 3–6 actionable steps.
5. **Real-Time WebSockets & Bi-Directional Telegram Sync**:
   - WebSocket stream (`/ws/tasks`) backed by Redis Pub/Sub (`tasks:events`) strictly scopes real-time broadcasts to the task owner and authorized `@username` collaborators.
   - Web dashboard edits trigger `notify_telegram_on_web_change` to edit the existing Telegram task card in place (or send a reply notification) for the owner and mentioned collaborators.
6. **Resilient Telegram Webhook Registration**:
   - On FastAPI startup, webhook registration runs asynchronously in the background with automatic retry/backoff (`register_telegram_webhook_with_retry`) so Uvicorn boots immediately even while DNS or Let's Encrypt TLS is still provisioning.
   - Provides `POST /api/v1/telegram/register-webhook` (protected by `X-Telegram-Bot-Api-Secret-Token`) to manually re-trigger webhook registration at any time.

---

## Repository Structure

```text
.
├── .env.example
├── .env.prod.example
├── .gitignore
├── .pre-commit-config.yaml
├── Caddyfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── README.md
├── .github/
│   └── workflows/
│       └── ci-cd.yml
├── scripts/
│   └── setup_dev.sh
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 0001_initial_schema.py
│   │       └── 0002_add_priority_and_tags.py
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── api/
│   │   ├── bot/
│   │   ├── services/
│   │   └── worker/
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── index.html
    └── src/
```

---

## Local Quick Start with Docker Compose

1. Copy `.env.example` to `.env` and populate `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`, and `OPENAI_API_KEY`:
   ```bash
   cp .env.example .env
   ```
2. Launch PostgreSQL, Redis, FastAPI Backend, Celery Worker, and Nginx/React Frontend:
   ```bash
   docker compose up --build -d
   ```
3. (Optional) Start with the Cloudflare Tunnel sidecar for local webhook testing:
   ```bash
   docker compose --profile tunnel up --build -d
   ```

---

## Local Development, Static Analysis & Testing

1. Initialize the `.venv` virtual environment, install dependencies, and configure pre-commit hooks:
   ```bash
   sh scripts/setup_dev.sh
   ```
2. Run static analysis and the automated test suite (enforcing >=80% line coverage):
   ```bash
   cd backend
   ../.venv/bin/ruff check app tests
   ../.venv/bin/ruff format --check app tests
   ../.venv/bin/mypy app tests
   ../.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=80
   ```
