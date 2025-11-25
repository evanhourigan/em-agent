# Deployment Guide - v1.0.0

Production deployment guide for EM Agent.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Configuration](#environment-configuration)
3. [Database Setup](#database-setup)
4. [Docker Deployment](#docker-deployment)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Webhook Configuration](#webhook-configuration)
7. [Security Hardening](#security-hardening)
8. [Monitoring & Observability](#monitoring--observability)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

**Minimum Requirements:**
- Docker 20.10+ or Kubernetes 1.20+
- PostgreSQL 15+ (managed or self-hosted)
- 2GB RAM minimum (4GB recommended)
- 2 CPU cores minimum

**Optional:**
- Redis (for Celery workers)
- NATS (for event bus)
- OpenTelemetry collector (for tracing)
- Prometheus + Grafana (for metrics)

---

## Environment Configuration

### Required Variables

```bash
# Database (REQUIRED)
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname

# Application
ENV=production
APP_NAME="EM Agent Gateway"
APP_VERSION=1.0.0
```

### Production Security

```bash
# CORS - Set specific origins (NEVER use * in production)
CORS_ALLOW_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
CORS_ALLOW_HEADERS=*
CORS_MAX_AGE=600

# Authentication (Recommended for production)
AUTH_ENABLED=true
JWT_SECRET_KEY=your-secret-key-min-32-chars-random-string
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MIN=120
MAX_PAYLOAD_BYTES=1048576  # 1MB

# Safety Limits
MAX_DAILY_SLACK_POSTS=1000
MAX_DAILY_RAG_SEARCHES=5000
```

### Slack Integration

```bash
# For webhook notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# OR for bot token (more features)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_DEFAULT_CHANNEL=#engineering

# Signature verification (REQUIRED in production)
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_SIGNING_REQUIRED=true
```

### Integration Feature Flags

```bash
# Enable/disable integrations as needed
INTEGRATIONS_GITHUB_ENABLED=true
INTEGRATIONS_JIRA_ENABLED=true
INTEGRATIONS_SHORTCUT_ENABLED=true
INTEGRATIONS_LINEAR_ENABLED=true
INTEGRATIONS_PAGERDUTY_ENABLED=true
INTEGRATIONS_SLACK_ENABLED=true
INTEGRATIONS_DATADOG_ENABLED=true
INTEGRATIONS_SENTRY_ENABLED=true
INTEGRATIONS_CIRCLECI_ENABLED=true
INTEGRATIONS_JENKINS_ENABLED=true
INTEGRATIONS_GITLAB_ENABLED=true
INTEGRATIONS_KUBERNETES_ENABLED=true
INTEGRATIONS_ARGOCD_ENABLED=true
INTEGRATIONS_ECS_ENABLED=true
INTEGRATIONS_HEROKU_ENABLED=true
INTEGRATIONS_CODECOV_ENABLED=true
INTEGRATIONS_SONARQUBE_ENABLED=true
```

### Observability (Optional)

```bash
# OpenTelemetry Tracing
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318

# LLM Summarization (Optional)
AGENT_LLM_ENABLED=true
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

---

## Database Setup

### PostgreSQL Setup

```bash
# Create database
psql -U postgres -c "CREATE DATABASE em_agent;"

# Create user (if needed)
psql -U postgres -c "CREATE USER em_agent WITH PASSWORD 'secure-password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE em_agent TO em_agent;"

# Enable required extensions
psql -U em_agent -d em_agent -c "CREATE EXTENSION IF NOT EXISTS pgvector;"
```

### Run Migrations

```bash
# Using Docker
docker compose run --rm gateway alembic upgrade head

# Or directly
cd services/gateway
alembic upgrade head
```

### Connection Pooling

The gateway uses SQLAlchemy connection pooling with these defaults:
- `pool_size=5` - Base connection pool size
- `max_overflow=5` - Additional connections under load
- `pool_pre_ping=True` - Health check connections before use

For high-traffic deployments, adjust in `services/gateway/app/db.py`:

```python
_engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=10,      # Increase for high traffic
    max_overflow=10,   # Increase for burst capacity
    future=True,
)
```

---

## Docker Deployment

### Production Docker Compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  gateway:
    image: em-agent/gateway:1.0.0
    build:
      context: ./services/gateway
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - ENV=production
      - DATABASE_URL=${DATABASE_URL}
      - CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS}
      - AUTH_ENABLED=true
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
      - SLACK_SIGNING_REQUIRED=true
      - RATE_LIMIT_ENABLED=true
      - OTEL_ENABLED=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_ENDPOINT}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  db:
    image: pgvector/pgvector:pg15
    environment:
      - POSTGRES_DB=em_agent
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### Deploy

```bash
# Load environment
export $(cat .env.production | xargs)

# Build and start
docker compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker compose -f docker-compose.prod.yml exec gateway alembic upgrade head

# Check health
curl http://localhost:8000/health
```

---

## Kubernetes Deployment

### ConfigMap

`k8s/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: em-agent-config
  namespace: em-agent
data:
  ENV: "production"
  APP_NAME: "EM Agent Gateway"
  APP_VERSION: "1.0.0"
  RATE_LIMIT_ENABLED: "true"
  RATE_LIMIT_PER_MIN: "120"
  AUTH_ENABLED: "true"
  CORS_ALLOW_ORIGINS: "https://yourdomain.com"
```

### Secret

`k8s/secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: em-agent-secrets
  namespace: em-agent
type: Opaque
stringData:
  DATABASE_URL: postgresql+psycopg://user:pass@postgres:5432/em_agent
  JWT_SECRET_KEY: your-secret-key-min-32-chars
  SLACK_SIGNING_SECRET: your-slack-secret
  SLACK_WEBHOOK_URL: https://hooks.slack.com/services/YOUR/WEBHOOK
```

### Deployment

`k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: em-agent-gateway
  namespace: em-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: em-agent-gateway
  template:
    metadata:
      labels:
        app: em-agent-gateway
    spec:
      containers:
      - name: gateway
        image: em-agent/gateway:1.0.0
        ports:
        - containerPort: 8000
          name: http
        envFrom:
        - configMapRef:
            name: em-agent-config
        - secretRef:
            name: em-agent-secrets
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
```

### Service

`k8s/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: em-agent-gateway
  namespace: em-agent
spec:
  type: LoadBalancer
  selector:
    app: em-agent-gateway
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
    name: http
```

### Ingress

`k8s/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: em-agent-ingress
  namespace: em-agent
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "120"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - em-agent.yourdomain.com
    secretName: em-agent-tls
  rules:
  - host: em-agent.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: em-agent-gateway
            port:
              number: 80
```

### Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace em-agent

# Apply configs
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# Run migrations (one-time job)
kubectl run -n em-agent migrations \
  --image=em-agent/gateway:1.0.0 \
  --restart=Never \
  --env-from=secret/em-agent-secrets \
  --command -- alembic upgrade head

# Check status
kubectl get pods -n em-agent
kubectl logs -n em-agent deployment/em-agent-gateway
```

---

## Webhook Configuration

### Configure Webhooks in Each Platform

**GitHub:**
1. Go to repo Settings → Webhooks → Add webhook
2. Payload URL: `https://your-domain/webhooks/github`
3. Content type: `application/json`
4. Events: Pull requests, Issues, Workflow runs
5. Secret: (optional but recommended)

**Jira:**
1. Jira Settings → System → WebHooks
2. URL: `https://your-domain/webhooks/jira`
3. Events: Issue created, updated, deleted

**Slack:**
1. Create Slack App at api.slack.com/apps
2. Event Subscriptions → Enable
3. Request URL: `https://your-domain/webhooks/slack`
4. Subscribe to: `message.channels`, `reaction_added`, `app_mention`

**CircleCI:**
1. Project Settings → Webhooks
2. URL: `https://your-domain/webhooks/circleci`
3. Events: workflow-completed, job-completed

**ArgoCD:**
1. Settings → Webhook
2. URL: `https://your-domain/webhooks/argocd`

*(Similar process for all 18 integrations)*

---

## Security Hardening

### Production Checklist

- [ ] Set `ENV=production`
- [ ] Configure specific `CORS_ALLOW_ORIGINS` (not `*`)
- [ ] Enable `AUTH_ENABLED=true` with strong JWT secret (32+ chars)
- [ ] Set `SLACK_SIGNING_REQUIRED=true` with valid secret
- [ ] Enable rate limiting: `RATE_LIMIT_ENABLED=true`
- [ ] Use HTTPS/TLS for all endpoints
- [ ] Store secrets in vault (HashiCorp Vault, AWS Secrets Manager, etc.)
- [ ] Enable database connection encryption
- [ ] Review integration feature flags (disable unused integrations)
- [ ] Set up network policies/firewalls
- [ ] Enable audit logging
- [ ] Regular security updates

### Secrets Management

**Option 1: HashiCorp Vault**
```bash
vault kv put secret/em-agent \
  database_url="postgresql://..." \
  jwt_secret="..." \
  slack_secret="..."
```

**Option 2: AWS Secrets Manager**
```bash
aws secretsmanager create-secret \
  --name em-agent/production \
  --secret-string '{"database_url":"...","jwt_secret":"..."}'
```

**Option 3: Kubernetes Secrets**
```bash
kubectl create secret generic em-agent-secrets \
  --from-literal=database-url="postgresql://..." \
  --from-literal=jwt-secret="..."
```

### Network Security

```yaml
# Kubernetes NetworkPolicy example
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: em-agent-network-policy
spec:
  podSelector:
    matchLabels:
      app: em-agent-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP
      port: 443   # HTTPS
```

---

## Monitoring & Observability

### Prometheus Metrics

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'em-agent'
    static_configs:
      - targets: ['em-agent-gateway:8000']
    metrics_path: /metrics
```

**Key Metrics to Monitor:**
- `http_requests_total` - Request count by endpoint
- `http_request_duration_seconds` - Request latency
- `approvals_decisions_total` - Approval decisions
- `workflows_auto_vs_hitl_total` - Automation ratio
- `db_connection_pool_*` - Connection pool health
- `process_resident_memory_bytes` - Memory usage

### Grafana Dashboard

Import the included dashboard: `docs/grafana-dashboard.json`

**Panels:**
1. Request rate & latency
2. DORA metrics (deployment frequency, lead time, CFR, MTTR)
3. Database connection pool
4. Error rates by endpoint
5. Integration health (enabled/disabled)

### OpenTelemetry Tracing

```bash
# docker-compose.prod.yml
services:
  tempo:
    image: grafana/tempo:latest
    ports:
      - "4318:4318"  # OTLP gRPC
      - "3200:3200"  # Tempo query
    volumes:
      - ./tempo-config.yaml:/etc/tempo.yaml
    command: ["-config.file=/etc/tempo.yaml"]

  gateway:
    environment:
      - OTEL_ENABLED=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318
```

### Logging

**Structured logs** are emitted in JSON format:

```json
{
  "timestamp": "2025-11-24T12:00:00Z",
  "level": "info",
  "message": "request.completed",
  "path": "/webhooks/github",
  "method": "POST",
  "status": 200,
  "duration_ms": 45.2
}
```

**Aggregate logs** with:
- Loki + Grafana
- Elasticsearch + Kibana
- CloudWatch Logs
- Datadog Logs

---

## Backup & Recovery

### Database Backups

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="em_agent_backup_$DATE.sql"

pg_dump -U em_agent em_agent > $BACKUP_FILE
gzip $BACKUP_FILE

# Upload to S3
aws s3 cp $BACKUP_FILE.gz s3://your-backup-bucket/em-agent/

# Retention: keep last 30 days
find . -name "em_agent_backup_*.sql.gz" -mtime +30 -delete
```

### Restore

```bash
# Download backup
aws s3 cp s3://your-backup-bucket/em-agent/em_agent_backup_YYYYMMDD.sql.gz .
gunzip em_agent_backup_YYYYMMDD.sql.gz

# Restore
psql -U em_agent em_agent < em_agent_backup_YYYYMMDD.sql
```

### Disaster Recovery

1. **Database snapshots** - Automated daily snapshots
2. **Configuration backup** - Store in version control
3. **Secret backup** - Encrypted backups in vault
4. **Recovery Time Objective (RTO)** - < 1 hour
5. **Recovery Point Objective (RPO)** - < 24 hours

---

## Troubleshooting

### Health Check Failing

```bash
# Check logs
docker compose logs gateway

# Verify database connectivity
docker compose exec gateway python -c "from app.db import check_database_health; print(check_database_health())"

# Check environment
docker compose exec gateway env | grep DATABASE_URL
```

### High Memory Usage

```bash
# Check current usage
docker stats gateway

# Reduce connection pool size in db.py
pool_size=3
max_overflow=3

# Or increase container limits
docker update --memory="4g" gateway
```

### Webhook Delivery Failures

```bash
# Check logs for specific integration
docker compose logs gateway | grep "source=github"

# Verify integration is enabled
curl http://localhost:8000/health

# Test webhook locally
curl -X POST http://localhost:8000/webhooks/github \
  -H 'X-GitHub-Event: ping' \
  -H 'X-GitHub-Delivery: test-1' \
  -d '{"zen":"Keep it simple"}'
```

### Database Connection Pool Exhausted

```bash
# Check active connections
psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname='em_agent';"

# Kill idle connections
psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='em_agent' AND state='idle';"

# Increase pool size in db.py or reduce load
```

### Rate Limit Issues

```bash
# Check rate limit settings
curl -I http://localhost:8000/health
# Look for X-RateLimit-* headers

# Adjust per environment
RATE_LIMIT_PER_MIN=240 docker compose up -d gateway

# Or disable for trusted internal traffic
RATE_LIMIT_ENABLED=false
```

---

## Production Readiness Checklist

### Before Launch

- [ ] Database migrations applied
- [ ] All integrations configured and tested
- [ ] CORS configured for production domains
- [ ] JWT authentication enabled with secure secret
- [ ] Slack signing verification enabled
- [ ] Rate limiting configured
- [ ] HTTPS/TLS certificates installed
- [ ] Secrets stored securely (vault/secrets manager)
- [ ] Monitoring configured (Prometheus + Grafana)
- [ ] Logging aggregation set up
- [ ] Backup automation configured
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Security review completed

### Post-Launch Monitoring

- Monitor `/health` and `/ready` endpoints
- Track error rates in logs
- Monitor DORA metrics dashboards
- Review webhook delivery success rates
- Check database connection pool health
- Monitor memory and CPU usage
- Review rate limit hit rates
- Track API response times

---

For API reference, see [API_REFERENCE.md](./API_REFERENCE.md).
