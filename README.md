Engineering Manager Agent - Quickstart

Prereqs

- Docker Desktop running
- Homebrew with docker-compose installed: `brew install docker-compose`

Run (gateway + db)

```bash
make up
```

Check status

```bash
make ps
```

Follow logs

```bash
make logs
```

Health check

```bash
make health
# or
curl -sS http://localhost:8000/health
```

Metrics (Prometheus format)

```bash
make metrics
# or
curl -sS http://localhost:8000/metrics | head -50
```

Stop and clean

```bash
make down
```

Notes

- The gateway FastAPI app exposes `/` (info), `/health`, and `/metrics`.
- Postgres DSN is injected via `DATABASE_URL` from `docker-compose.yml`.
