# Pole Fault Monitoring Backend

FastAPI service for monitoring smart electricity poles, collecting node health data, surfacing faults, and notifying maintenance staff via Firebase Cloud Messaging (FCM) and email. The API stores device registrations, pole (node) metadata, and reported faults while exposing RESTful endpoints for field devices, dashboards, and admin tooling.

## Features

- FastAPI + SQLAlchemy stack with SQLite by default (PostgreSQL/MySQL ready through `DB_URL`).
- Node heartbeat tracking with background monitor that marks stale poles as faulty.
- Fault reporting workflow that records incidents, uploads imagery, and notifies staff via push/email.
- Device registration endpoint that keeps track of FCM tokens per user role (citizen vs staff).
- Configurable CORS, API-key auth, logging, and upload directory via environment variables.
- Dockerfile for reproducible deployments plus `requirements.txt` for local development.

## Tech Stack

| Layer           | Details                                                                            |
| --------------- | ---------------------------------------------------------------------------------- |
| API             | FastAPI, Pydantic v1/v2 compatible schemas                                         |
| Persistence     | SQLAlchemy ORM, SQLite default (`faults.db`), optional Postgres/MySQL via `DB_URL` |
| Notifications   | Firebase Admin SDK for FCM, SMTP email via `notification_utils.py`                 |
| Background jobs | Async heartbeat monitor started on FastAPI startup                                 |
| Deployment      | Gunicorn + Uvicorn workers (Docker)                                                |

## Project Layout

```
├─ crud.py               # Database helpers for devices/nodes/faults
├─ database.py           # SQLAlchemy engine/session setup
├─ main.py               # FastAPI app, routes, middleware, background tasks
├─ models.py             # ORM models (Device, Node, Fault)
├─ notification_utils.py # Email notifications via SMTP
├─ fcm_utils.py          # Firebase Cloud Messaging helpers
├─ schemas.py            # Pydantic schemas & validators
├─ uploads/              # Stored media from /api/v1/upload
├─ requirements.txt
├─ Dockerfile
└─ serviceAccountKey.json (local dev credentials, do not commit)
```

## Getting Started

1. **Clone & enter the repo**
   ```pwsh
   git clone <your-fork-url>
   cd sih_project_backend
   ```
2. **Create a virtual environment (optional but recommended)**
   ```pwsh
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. **Install dependencies**
   ```pwsh
   pip install -r requirements.txt
   ```
4. **Provide configuration** (see [Environment](#environment)). Copy `.env.example` (create one via the section below) to `.env` or export variables in your shell.
5. **Run the API**
   ```pwsh
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
6. Open http://127.0.0.1:8000/docs for interactive Swagger UI.

## Environment

Create an `.env` file alongside `main.py` (the project already loads it via `python-dotenv`). Only set what you need; sensible defaults exist for local use.

| Variable                           | Description                                          | Default                  |
| ---------------------------------- | ---------------------------------------------------- | ------------------------ |
| `API_KEY`                          | Optional header (`X-API-Key`) to guard all endpoints | empty (auth disabled)    |
| `DB_URL`                           | SQLAlchemy database URL                              | `sqlite:///faults.db`    |
| `CORS_ALLOW_ORIGINS`               | Comma-separated list of allowed origins              | preset list in `main.py` |
| `LOG_LEVEL`                        | Python logging level                                 | `INFO`                   |
| `UPLOAD_DIR`                       | Directory path for uploaded media                    | `uploads/`               |
| `FIREBASE_CRED_PATH`               | Path to Firebase service account JSON                | `serviceAccountKey.json` |
| `SMTP_SERVER` / `SMTP_PORT`        | Mail server details                                  | `smtp.gmail.com` / `587` |
| `EMAIL_USER` / `EMAIL_PASSWORD`    | SMTP auth (use app password for Gmail)               | none                     |
| `RECIPIENT_EMAILS`                 | Comma-separated recipients for fault emails          | `vhschahal@gmail.com`    |
| `SEED_SAMPLE_NODES`                | `true/false` flag to pre-populate demo nodes         | `false`                  |
| `HEARTBEAT_MAX_AGE_SECONDS`        | Seconds before a node is marked faulty               | `300`                    |
| `HEARTBEAT_CHECK_INTERVAL_SECONDS` | Background sweep interval in seconds                 | `60`                     |

### Example `.env`

```
API_KEY=super-secret-key
DB_URL=postgresql+psycopg2://user:pass@localhost:5432/pole_db
FIREBASE_CRED_PATH=serviceAccountKey.json
EMAIL_USER=alerts@example.com
EMAIL_PASSWORD=app-password
RECIPIENT_EMAILS=ops@example.com,it@example.com
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:5173
SEED_SAMPLE_NODES=true
```

## Running with Docker

```
docker build -t pole-fault-backend .
docker run --rm -p 8000:8000 --env-file .env pole-fault-backend
```

Adjust the `.env` path or pass `-e KEY=value` pairs for deployment. Remember to mount secrets (Firebase credential JSON) if the container needs them.

## API Overview

| Method | Path                       | Purpose                                              |
| ------ | -------------------------- | ---------------------------------------------------- |
| `POST` | `/api/v1/devices/register` | Register or update a device/FCM token.               |
| `GET`  | `/api/v1/nodes`            | List nodes ordered by most recent update.            |
| `POST` | `/api/v1/nodes/update`     | Update node status/location; creates node if absent. |
| `POST` | `/api/v1/faults/report`    | Create a fault record and trigger notifications.     |
| `GET`  | `/api/v1/faults`           | List recorded faults (latest first).                 |
| `GET`  | `/api/v1/stats`            | Aggregate counts and fault percentage.               |
| `POST` | `/api/v1/upload`           | Upload an image/file and receive a relative URL.     |
| `GET`  | `/`                        | Health check.                                        |

Every endpoint (except `/`) honors the optional API-key guard. Include `X-API-Key: <API_KEY>` in requests when `API_KEY` is set.

### Sample Fault Report

```http
POST /api/v1/faults/report
Content-Type: application/json
X-API-Key: super-secret-key

{
  "node_id": 12,
  "description": "Arcing detected",
  "confidence": 92.5,
  "image_url": "https://cdn.example.com/poles/12.jpg"
}
```

## Notifications

- **Push**: `fcm_utils.py` initializes Firebase Admin using `serviceAccountKey.json`. Only staff devices (`role="staff"`) receive incident pushes.
- **Email**: `notification_utils.py` sends HTML emails to `RECIPIENT_EMAILS`. Provide SMTP credentials via env vars.

## Background Heartbeat Monitor

`main.py` starts an async task on startup that periodically checks `Node.last_updated`. Nodes that have not checked in within `HEARTBEAT_MAX_AGE_SECONDS` are auto-marked as `faulty` and trigger FCM notifications.

## Testing

```
pytest
```

Add unit tests under a `tests/` directory (not yet included) to cover CRUD helpers, notification utilities (with mocks), and API routes.

## Deployment Notes

- Gunicorn command in the `Dockerfile` runs two Uvicorn workers; tune worker count via `-w` or environment variables depending on target CPU.
- Mount persistent storage for uploads (`UPLOAD_DIR`) if you keep images locally, or adapt `/api/v1/upload` to push to object storage.
- Keep `serviceAccountKey.json` and `.env` out of version control; use secrets management in CI/CD.

## Contributing

1. Fork and branch (`git checkout -b feature/my-change`).
2. Run `pytest` and linting tools before pushing.
3. Open a pull request summarizing changes and testing status.

## License

Add your preferred license (MIT, Apache-2.0, etc.) before publishing to GitHub.
# fault-detector-backend
