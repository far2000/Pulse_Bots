# Pulse Bots — News (Phase 1)

A multi-bot Telegram aggregator. Phase 1 ships the **news bot**: a Telethon
userbot reads source channels, media is processed and stored in MinIO,
Gemini 2.0 Flash rewrites/summarizes the text, and an aiogram bot publishes
to our own channel.

The `shared/` package is bot-agnostic — phases 2–4 (sports / cars / prices)
will reuse it by registering new source channels and wiring a new `bots/<name>/`
package.

---

## Architecture

```
                ┌──────────────────────────┐
 source TG ──▶  │  Telethon userbot        │
 channels       │  (events.NewMessage +    │
                │   periodic catch-up)     │
                └────────┬─────────────────┘
                         │  parsed message
                         ▼
                ┌──────────────────────────┐
                │  IngestPipeline          │
                │   dedup → download media │
                │   → image processing     │
                │   → MinIO upload         │
                │   → DB persist           │
                │   → Gemini summarize     │
                └────────┬─────────────────┘
                         │  Article (summarized)
                         ▼
                ┌──────────────────────────┐
                │  PublishLoop             │
                │   throttled aiogram bot  │
                │   → destination channel  │
                └──────────────────────────┘

   aiogram bot also exposes /start, /latest, /stats, /add_source …
```

Reading other channels needs **MTProto** (`Telethon`, user account).
Publishing & user commands use the **Bot API** (`aiogram`, bot token).
Both run in the same async process and share `shared/`.

---

## Repo layout

```
shared/                     # bot-agnostic, reused by every Pulse Bot
  config.py logging.py
  cache/                    # in-process TTL+LRU cache (dedup + Gemini cache)
  db/                       # async SQLAlchemy + models + repositories
  storage/                  # MinIO / local backends
  media/                    # image processor, dedup, type detection
  ingest/                   # Telethon client + message parser
  ai/                       # Summarizer interface + Gemini + versioned prompts
  publishers/               # Telegram publisher + HTML formatter
  utils/
bots/news/                  # news-bot specifics
  main.py app.py            # entrypoint + composition root
  reader.py pipeline.py     # Telethon events → pipeline → publish
  handlers/                 # /start, /latest, /stats, /add_source …
  middlewares.py jobs.py
migrations/                 # async Alembic
scripts/
  login_telethon.py         # one-time interactive login
  seed_sources.py
  init_db.py
Dockerfile docker-compose.yml
pyproject.toml .env.example
```

---

## Prerequisites

- Python **3.11+** and [`uv`](https://github.com/astral-sh/uv)
- Running PostgreSQL 16 and MinIO (or use `docker compose up postgres minio`)
- Telegram **API ID / API HASH** from <https://my.telegram.org>
- A **bot token** from `@BotFather`
- A **Gemini API key** from <https://aistudio.google.com/>
- A **dedicated Telegram account** for the userbot (never use your personal one)

---

## Local setup

```bash
# 1. clone & install
uv venv
uv pip install -e ".[dev]"

# 2. configure
cp .env.example .env
# Edit .env — fill TELEGRAM_API_ID, TELEGRAM_API_HASH, BOT_TOKEN,
# DESTINATION_CHANNEL_ID, ADMIN_IDS, AVALAI_API_KEY, and DB/MinIO URLs.

# 3. spin up the data plane (only needed locally)
docker compose up -d postgres minio

# 4. migrate
uv run alembic upgrade head

# 5. create the Telethon session (one-time, interactive)
uv run python scripts/login_telethon.py
# Copy the printed TELETHON_SESSION=... into .env

# 6. seed your source channels
$EDITOR scripts/seed_sources.py    # add (username, title) tuples
uv run python scripts/seed_sources.py

# 7. add the bot as an admin in the destination channel,
#    then run the bot
uv run python -m bots.news
```

You should see:

```
Telethon connected as: id=… username=…
Resolved N source channels
Publish loop started (importance>=2).
All components started.
```

---

## Operating notes

### Telethon userbot ban risk

Reading from channels you don't own with a user account is a **gray area**
in Telegram's ToS. To minimize the chance of bans:

- Use a **dedicated** account, not your personal one.
- Subscribe (join) each source channel manually with the account, then add
  it to `source_channels` — the userbot will only see channels its account
  is a member of.
- Keep traffic reasonable — the catch-up sweep defaults to 50 msgs/source
  every 15 minutes.
- Watch for `FloodWaitError` in logs and back off if you see them often.

### Adding new sources at runtime

Admins (`ADMIN_IDS` in `.env`) can:

```
/add_source @some_channel
/add_source -1001234567890
/list_sources
/toggle_source <uuid>
/stats
```

The reader auto-resolves entity ids on the next catch-up sweep.

### Where data goes

- **PostgreSQL** — all metadata, dedup truth, idempotency, audit logs
- **In-memory cache** — Gemini summary cache + content/file dedup hints
  (process-local; Postgres unique constraints are the truth)
- **aiogram MemoryStorage** — FSM state (process-local)
- **MinIO** — processed images (WebP) and videos, keyed by
  `news/yyyy/mm/dd/<sha256>.<ext>` (plus `_thumb.webp` for images).
  Make sure `MINIO_PUBLIC_DOMAIN` is reachable from Telegram's servers — the
  publisher sends asset URLs, it does not re-upload bytes.

### Failure modes

- **Bad source / blocked channel** → logged and skipped, others keep flowing.
- **Gemini failure** → the article is saved with `status=failed` and the
  `retry_failed_summaries` job will re-attempt every 10 min. The original text
  is preserved either way — we never drop the message.
- **Telegram rate limit on publish** → publisher honors `RetryAfter` once.
  Persistent failures are logged to `publish_logs` with the error.
- **Userbot offline** → the periodic catch-up job pulls everything new on
  reconnect using `source_channels.last_message_id`.

---

## Coolify deployment

1. Add the repo to Coolify and point it at the included `Dockerfile`
   (single-container deployment).
2. Set every variable from `.env.example` in the service's env config.
   `TELETHON_SESSION` is the session string you generated locally — paste it
   in once; the container will boot without any interactive login.
3. Point at your already-running PostgreSQL and MinIO services with the
   appropriate `DATABASE_URL` and `MINIO_*` variables.
4. (First deploy only) Open a one-off shell and run:
   ```
   uv run alembic upgrade head
   ```
   Or wire it into the container's command. After that, deploys are just:
   ```
   git push   →   Coolify rebuild   →   restart
   ```

---

## Adding the next bot (sports / cars / prices)

1. Create `bots/<name>/` mirroring `bots/news/`.
2. Set `BOT_TYPE` to the new enum value in `bots/<name>/config.py`.
3. Reuse every `shared/` component as-is.
4. Add a separate Coolify service (or run multiple bots from one process if
   they share a destination — see `BotType` discriminator on every table).

---

## Useful commands

```bash
# Create a new migration after model changes
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head

# Re-run the catch-up sweep manually (from a Python REPL)
python -c "import asyncio; from bots.news.app import NewsApp; ..."

# Tail logs
docker compose logs -f news-bot
```

---

## Tech stack

| Layer       | Choice                                     |
|-------------|--------------------------------------------|
| Userbot     | Telethon (MTProto, session string)         |
| Bot         | aiogram 3.x                                |
| DB          | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Cache / FSM | In-process TTL/LRU + aiogram MemoryStorage |
| Storage     | MinIO via aioboto3 (S3-compatible)         |
| Images      | Pillow → WebP (q85), thumbnails, EXIF stripped |
| LLM         | Gemini 2.0 Flash via Avalai (OpenAI-compatible) |
| Scheduling  | APScheduler (in-process)                   |
| Logging     | loguru                                     |
| Deps        | uv                                         |
