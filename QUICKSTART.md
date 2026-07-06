# Bilm Backend — Quick Start & Troubleshooting

## Fix Applied (what was wrong)

| Issue | Cause | Fix |
|---|---|---|
| `version` is obsolete warning | Old Compose spec field | Removed `version: "3.9"` line |
| `api` service not running | `env_file: .env` failed (no .env file existed) | Switched to inline `environment:` with `${VAR:-default}` syntax |
| Beat scheduler crash | Referenced `django_celery_beat` (not installed) | Replaced with built-in `celery beat` (no extra package) |
| Container startup crash | `StaticFiles` mount failed when directory missing | Added `os.makedirs(..., exist_ok=True)` before mount |

---

## Step-by-Step Start (Windows PowerShell / CMD)

```powershell
# 1 — Go to your project folder
cd C:\Users\USER\PycharmProjects\bilm\backend

# 2 — Stop and remove any broken containers
docker compose down -v

# 3 — Rebuild images cleanly (important after code changes)
docker compose build --no-cache

# 4 — Start all services
docker compose up -d

# 5 — Watch logs to confirm api is healthy
docker compose logs -f api
```

### Expected healthy output
```
bilm_api  | INFO:     Started server process
bilm_api  | INFO:     Waiting for application startup.
bilm_api  | INFO:     Application startup complete.
bilm_api  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## After First Start — Seed Database

```powershell
# Creates tables + inserts default email templates + admin user
docker compose exec api python -m app.seed
```

Default admin login:
- Email: `admin@bilmtechnical.com`
- Password: `ChangeMe2025!`  ← change immediately

---

## Verify Everything Is Running

```powershell
docker compose ps
```

Expected — all services `running` or `healthy`:
```
NAME           STATUS
bilm_api       running (healthy)
bilm_worker    running
bilm_beat      running
bilm_flower    running
bilm_db        running (healthy)
bilm_redis     running (healthy)
bilm_nginx     running
```

| Service | URL |
|---|---|
| API docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| Flower (Celery) | http://localhost:5555 |

---

## If `api` Still Fails — Diagnose

```powershell
# See the exact error
docker compose logs api

# Common errors and fixes:
# "could not connect to server" → db not healthy yet, wait 30s and retry
# "password authentication failed" → DB volume from old run, fix:
docker compose down -v   # -v removes volumes, wipes DB
docker compose up -d

# Module not found errors → rebuild
docker compose build --no-cache api
docker compose up -d api
```

---

## Email Setup (Gmail)

1. Go to https://myaccount.google.com/apppasswords
2. Create an App Password for "Mail"
3. Copy the 16-character password
4. Set in your environment or `.env`:

```
SMTP_USER=Biali.kandi@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop    ← the 16-char app password
```

Then restart: `docker compose restart api worker`
