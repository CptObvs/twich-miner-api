# Twitch Miner Backend

> **REST API for [Twitch-Channel-Points-Miner-v2](https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2)**
> FastAPI backend for managing multiple miner instances with JWT authentication and real-time log streaming.

## Features

- Multi-user support with JWT authentication
- Instance management (create, start, stop, configure)
- Real-time log streaming via Server-Sent Events
- Persistent Twitch authentication per instance

## Quick Start

```bash
# 1. Setup
git clone <your-repo-url>
cd python-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: Set MINER_REPO_PATH and JWT_SECRET

# 3. Run
./scripts/start.sh  # Windows: scripts\start.bat
```

**API Docs:** http://localhost:8000/docs (configurable via `DOCS_URL` in `.env`)

## Production

```bash
cp .env.prod .env
# Edit .env: Configure MINER_REPO_PATH and CORS_ORIGINS
./scripts/start-prod.sh  # Windows: scripts\start-prod.bat
```

## Stream Logs

```bash
# Real-time log streaming via SSE
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/instances/{id}/logs
```

Full API documentation path configurable via `DOCS_URL` env variable (default: `/docs`). Change to a non-obvious path for security.

## License

MIT
