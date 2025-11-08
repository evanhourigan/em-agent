# EM Agent: Architecture Deep Dive

**A Comprehensive Guide to Design Decisions, Technology Choices, and System Architecture**

---

## Table of Contents

1. [Product Vision & Business Context](#1-product-vision--business-context)
2. [Core Architecture Principles](#2-core-architecture-principles)
3. [Technology Stack: The Why Behind Every Choice](#3-technology-stack-the-why-behind-every-choice)
4. [System Architecture Overview](#4-system-architecture-overview)
5. [Component Deep Dives](#5-component-deep-dives)
6. [Data Flow & Integration Patterns](#6-data-flow--integration-patterns)
7. [Observability & Operations](#7-observability--operations)
8. [Security & Compliance](#8-security--compliance)
9. [Testing Strategy](#9-testing-strategy)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Trade-offs & Alternatives Considered](#11-trade-offs--alternatives-considered)
12. [Scaling & Performance Considerations](#12-scaling--performance-considerations)
13. [Future Roadmap & Evolution](#13-future-roadmap--evolution)

---

## 1. Product Vision & Business Context

### The Problem Space

Engineering teams face a critical challenge: **information overload combined with lack of actionable insights**. Engineering managers spend countless hours:
- Manually tracking DORA metrics across fragmented tools
- Identifying stale PRs and workflow bottlenecks through ad-hoc queries
- Responding to incidents without historical context
- Making decisions without comprehensive operational visibility

**The core insight:** Most engineering teams have the data but lack the automation and intelligence to act on it effectively.

### The Solution: EM Agent

EM Agent is designed as an **"AI-assisted Chief of Staff"** for engineering organizations. The key design philosophy:

1. **Human-in-the-Loop (HITL) by Default** - Never fully automate decisions that require judgment. Always provide humans with context, recommendations, and approval workflows.

2. **Trust Through Transparency** - Every metric is auditable, every action is logged, every recommendation shows its reasoning.

3. **Progressive Enhancement** - Start with basic automation (notifications, reports) and progressively add intelligence (RAG-powered insights, policy engines, workflow automation).

4. **Integration-First** - Meet teams where they are (Slack, GitHub, Jira) rather than requiring new tools or processes.

### Target Personas

- **Engineering Managers (Primary)**: Need operational visibility, team health metrics, and automated toil reduction
- **Tech Leads**: Want workflow bottleneck identification and code review efficiency tracking
- **Platform Teams**: Require deployment frequency, failure rate tracking, and incident response automation
- **Engineering Directors**: Need portfolio-level metrics and cross-team insights

---

## 2. Core Architecture Principles

### Principle 1: Composability Over Monolith

**Decision:** Build as a collection of loosely-coupled services rather than a monolithic application.

**Rationale:**
- Different components have different scaling characteristics (gateway vs. RAG vs. workers)
- Teams can adopt features incrementally (start with metrics, add Slack later)
- Technology choices can be optimized per-service (FastAPI for API, sentence-transformers for RAG)
- Easier to test, deploy, and maintain in isolation

**Trade-off:** Added complexity of service orchestration, but Docker Compose makes local development simple and Kubernetes deployment straightforward.

### Principle 2: Events as the Source of Truth

**Decision:** Use event sourcing patterns with raw events stored in `events_raw` table.

**Rationale:**
- Engineering data (deploys, PRs, incidents) is inherently event-driven
- Raw events provide audit trail and enable metric recomputation
- dbt transformations can evolve without losing historical data
- Enables future event replay for analytics and ML features

**Implementation:** Webhooks → events_raw → dbt models → metrics APIs

### Principle 3: Policy as Code

**Decision:** Separate policy evaluation from execution using OPA (Open Policy Agent).

**Rationale:**
- Engineering policies change frequently (approval thresholds, deployment gates)
- Business logic should be declarative and version-controlled
- Non-engineers (managers, compliance) can review and approve policy changes
- Enable A/B testing of policy effectiveness

**Example:** Stale PR detection threshold can be configured in YAML without code changes.

### Principle 4: Observability from Day One

**Decision:** Instrument every component with structured logging, metrics, and tracing from initial development.

**Rationale:**
- Production issues in an "ops automation tool" erode trust immediately
- Prometheus metrics enable SLA monitoring and alerting
- OpenTelemetry tracing helps debug distributed workflows
- Secret redaction prevents compliance violations

**Implementation:** Prometheus + structured logging + OpenTelemetry spans throughout codebase.

---

## 3. Technology Stack: The Why Behind Every Choice

### Backend Framework: FastAPI

**Why FastAPI over Flask/Django?**

1. **Type Safety**: Pydantic models provide automatic validation and documentation
2. **Performance**: ASGI-based, comparable to Node.js/Go for I/O-bound workloads
3. **Developer Experience**: Auto-generated OpenAPI docs reduce documentation burden
4. **Async Support**: Native async/await for I/O operations (webhooks, external APIs)
5. **Industry Momentum**: Strong adoption in ML/data engineering teams (our target users)

**Trade-off:** Smaller ecosystem than Flask, but core functionality is sufficient.

### Database: PostgreSQL 15+ with pgvector

**Why PostgreSQL over MySQL/MongoDB?**

1. **Advanced SQL Features**: Window functions, CTEs, JSONB enable complex DORA metric queries
2. **pgvector Extension**: Native vector similarity search for RAG without separate vector DB
3. **ACID Guarantees**: Critical for approval workflows and financial metrics (deployment cost tracking)
4. **Ecosystem Maturity**: SQLAlchemy ORM, Alembic migrations, dbt support
5. **Cost Efficiency**: Single database for both relational and vector data

**Why pgvector over Pinecone/Weaviate?**
- Operational simplicity: One database instead of two
- Lower cost: No external service fees
- Sufficient performance for <100K documents (typical eng team knowledge base size)

### ORM: SQLAlchemy 2.0

**Why SQLAlchemy over raw SQL/other ORMs?**

1. **Flexibility**: Can drop to raw SQL for complex analytics while maintaining ORM for CRUD
2. **Type Safety**: Works well with mypy/Pydantic for end-to-end type checking
3. **Migration Support**: Alembic provides robust schema versioning
4. **Performance**: 2.0's new API is significantly faster than 1.x
5. **Industry Standard**: Extensive documentation and community support

**Pattern:** Use ORM for writes, raw SQL for complex read analytics (DORA metrics).

### Metrics Layer: dbt (data build tool)

**Why dbt over custom SQL scripts?**

1. **Testability**: Built-in testing framework for data quality (schema tests, not-null checks)
2. **Dependency Management**: Automatic DAG construction ensures metrics build in correct order
3. **Documentation**: Models self-document with schema.yml files
4. **Reusability**: Macros reduce SQL duplication across metric calculations
5. **Version Control**: SQL is code, enabling standard development workflows

**Example:** DORA metrics (lead time, deploy frequency, CFR, MTTR) are dbt models with tests.

### Message Queue: NATS

**Why NATS over RabbitMQ/Kafka?**

1. **Simplicity**: Single binary, minimal configuration, sub-second startup
2. **Performance**: 11M msgs/sec throughput, microsecond latencies
3. **Cloud-Native**: JetStream provides persistence without operational complexity
4. **Lightweight**: Perfect for <100K events/day (typical eng team scale)
5. **Developer Experience**: Easy local development, no Zookeeper/clustering overhead

**Trade-off:** Less mature ecosystem than Kafka, but sufficient for event distribution.

### Task Queue: Celery + Redis

**Why Celery for async tasks?**

1. **Battle-Tested**: 10+ years of production use, well-understood failure modes
2. **Flexibility**: Supports retries, rate limiting, task prioritization
3. **Monitoring**: Flower UI provides real-time task visibility
4. **Python-Native**: Seamless integration with FastAPI codebase

**Why Redis as broker?**
- Simple to operate (vs. RabbitMQ's complexity)
- Fast (in-memory, low latency)
- Dual-purpose: Also used for caching and session storage

### Workflow Orchestration: Temporal

**Why Temporal for long-running workflows?**

1. **Durability**: Workflows survive worker crashes, restarts, deployments
2. **Visibility**: Built-in UI for workflow inspection and debugging
3. **Complex Workflows**: Support for human approval steps (critical for EM Agent)
4. **Testing**: Deterministic workflow replay enables comprehensive testing
5. **Vendor-Agnostic**: Open-source, can self-host or use Temporal Cloud

**Use Case:** Multi-day approval workflows (e.g., "deploy if no incidents in 48h")

**Trade-off:** More complex than Celery, but necessary for stateful, long-running processes.

### RAG (Retrieval-Augmented Generation): Custom Implementation

**Why Custom RAG vs. LangChain/LlamaIndex?**

1. **Control**: Exact control over chunking, indexing, retrieval strategies
2. **Performance**: No framework overhead, optimized for our use case
3. **Flexibility**: Can switch between TF-IDF (fast, free) and embeddings (better quality)
4. **Simplicity**: <500 lines of code vs. heavy framework dependencies
5. **Cost**: TF-IDF baseline requires no LLM API calls

**Dual-Mode Design:**
- **TF-IDF Mode (Default)**: Fast, zero-cost, good enough for keyword search
- **Vector Mode (Optional)**: sentence-transformers embeddings + pgvector for semantic search

**Progressive Enhancement:** Start with TF-IDF, upgrade to vectors as knowledge base grows.

### Frontend/Admin UI: Flask + Jinja2

**Why Flask for admin UI?**

1. **Simplicity**: Render templates, no complex frontend build process
2. **Fast Development**: Jinja2 templates enable rapid UI iteration
3. **Minimal JS**: Server-side rendering reduces frontend complexity
4. **Python Alignment**: Same language as backend, easier hiring/maintenance

**Trade-off:** Not as rich as React/Vue, but sufficient for admin dashboards.

### Slack Integration: Native Slack SDK

**Why Slack as primary interface?**

1. **Context**: Users already live in Slack for communication
2. **Notifications**: Push model (alerts come to users) vs. pull (check dashboard)
3. **Interactive**: Block Kit enables rich approvals, buttons, workflows
4. **Adoption**: Zero training required, instant team rollout

**Design Pattern:** Every report/metric has both API endpoint and Slack command.

---

## 4. System Architecture Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Systems                         │
│  GitHub Webhooks  │  Jira Webhooks  │  Slack Events  │  Users  │
└────────┬─────────────────┬──────────────────┬──────────┬─────────┘
         │                 │                  │          │
         │                 │                  │          │
         v                 v                  v          v
┌────────────────────────────────────────────────────────────────┐
│                      API Gateway (FastAPI)                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Webhooks │  │  Signals  │  │  Policy  │  │  Slack Bot   │  │
│  │ Intake   │  │  Evaluator│  │  Engine  │  │  Commands    │  │
│  └────┬─────┘  └─────┬─────┘  └────┬─────┘  └──────┬───────┘  │
└───────┼──────────────┼─────────────┼────────────────┼──────────┘
        │              │             │                │
        v              v             v                v
┌───────────────────────────────────────────────────────────────┐
│                      Event Bus (NATS)                          │
│   events.github  │  signals.evaluated  │  approvals.requested │
└────────┬──────────────────┬─────────────────────┬─────────────┘
         │                  │                     │
         v                  v                     v
┌────────────────┐  ┌──────────────┐    ┌────────────────────┐
│  PostgreSQL    │  │  Workers     │    │  Temporal          │
│  ┌──────────┐  │  │  (Celery)    │    │  (Long Workflows)  │
│  │events_raw│  │  │  ┌────────┐  │    │  ┌──────────────┐  │
│  └────┬─────┘  │  │  │ Slack  │  │    │  │ Approval     │  │
│       │        │  │  │ Notify │  │    │  │ Workflows    │  │
│       v        │  │  └────────┘  │    │  └──────────────┘  │
│  ┌──────────┐  │  └──────────────┘    └────────────────────┘
│  │   dbt    │  │
│  │  Models  │  │         ┌──────────────────────┐
│  └────┬─────┘  │         │   RAG Service        │
│       │        │         │   (FastAPI)          │
│       v        │         │  ┌────────────────┐  │
│  ┌──────────┐  │         │  │  TF-IDF Index  │  │
│  │  DORA    │  │         │  │  or pgvector   │  │
│  │ Metrics  │  │         │  └────────────────┘  │
│  └──────────┘  │         └──────────────────────┘
└────────────────┘
         │                           │
         v                           v
┌────────────────────────────────────────────┐
│         Observability Stack                │
│  Prometheus  │  OpenTelemetry  │  Logs     │
└────────────────────────────────────────────┘
```

### Service Boundaries

Each service has a clear responsibility:

1. **Gateway**: API orchestration, authentication, routing
2. **RAG**: Knowledge retrieval and search
3. **Connectors**: External data ingestion (GitHub, Confluence crawlers)
4. **Workers**: Async task execution (notifications, reports)
5. **Temporal Workers**: Long-running stateful workflows
6. **Metrics (dbt)**: Transform raw events into analytics-ready metrics
7. **UI**: Admin dashboards for manual operations

**Key Insight:** Services communicate via APIs and events, never direct database access (except dbt).

---

## 5. Component Deep Dives

### 5.1 Gateway Service

**Responsibility:** Entry point for all external traffic, orchestrates business logic.

**Key Design Decisions:**

1. **Dependency Injection Pattern**
   - `get_db_session()` provides database sessions
   - `get_current_user()` handles authentication
   - FastAPI's native DI makes testing trivial (mock dependencies)

2. **Router Organization**
   - One router per domain (projects, approvals, signals, metrics)
   - Reduces merge conflicts, enables team ownership
   - Clear API surface area (GET /v1/approvals, POST /v1/workflows/run)

3. **Request/Response Models**
   - Pydantic schemas in `schemas/` directory
   - Automatic validation, serialization, documentation
   - Clear contract between frontend and backend

**Example: Approval Flow**
```python
POST /v1/workflows/run
  → Policy evaluation (should this be auto-approved?)
  → If auto: enqueue Celery task
  → If manual: create approval record, send Slack notification
  → Return approval_id for tracking
```

### 5.2 Database Schema Design

**Core Tables:**

1. **`events_raw`**: Immutable event store (webhook payloads)
   - Primary key: `delivery_id` (idempotency)
   - Indexed: `source`, `event_type`, `received_at`
   - Design: JSONB payload for flexibility, structured columns for querying

2. **`projects`**: Engineering teams/repositories
   - Soft deletes via `deleted_at` (audit compliance)
   - Indexed: `key` (unique identifier)

3. **`approvals`**: Human approval tracking
   - Foreign key to `workflow_jobs`
   - State machine: `pending → approved/rejected → completed`
   - Audit: `decided_by`, `decided_at`, `reason`

4. **`workflow_jobs`**: Async task queue
   - Polymorphic: `job_type` determines handling
   - Retries: `attempts`, `max_attempts`, `last_error`
   - Observability: `started_at`, `completed_at`, `duration_ms`

**Migration Strategy:**
- Alembic for version control
- Separate migrations for schema vs. data changes
- Rollback-safe (avoid `ALTER TABLE` without downgrade)

### 5.3 dbt Metrics Layer

**Model Structure:**

```
models/
├── dora_lead_time.sql       # PR open → deploy time
├── deployment_frequency.sql # Deploys per day/week
├── change_fail_rate.sql     # Failed deploys / total deploys
├── mttr.sql                 # Incident resolve time
├── wip.sql                  # Work-in-progress tracking
├── pr_idle_time.sql         # PR waiting for review time
└── schema.yml               # Tests and documentation
```

**Design Patterns:**

1. **Common Table Expressions (CTEs)**
   - Each metric builds incrementally
   - Easy to debug (query each CTE independently)
   - Self-documenting (named CTEs explain logic)

2. **Window Functions**
   - Calculate rolling averages (7-day deploy frequency)
   - Percentile metrics (P50/P95 lead time)
   - Team comparisons

3. **Data Quality Tests**
   ```yaml
   - name: dora_lead_time
     tests:
       - dbt_utils.recency:
           datepart: day
           interval: 1
       - unique:
           column_name: delivery_id
   ```

**Refresh Strategy:**
- Incremental models (process only new events)
- Daily batch refresh via `make dbt.run`
- Future: Real-time via dbt Cloud or Airflow

### 5.4 RAG Service Architecture

**Dual-Mode Design:**

**Mode 1: TF-IDF (Default)**
- In-memory sklearn TfidfVectorizer
- Startup: Load documents, fit vectorizer (~1 second for 1000 docs)
- Query: Transform query, compute cosine similarity, return top-k
- **Pros:** Fast, zero cost, deterministic
- **Cons:** No semantic understanding ("deploy failure" != "deployment error")

**Mode 2: Embeddings + pgvector (Optional)**
- sentence-transformers model (`all-MiniLM-L6-v2`)
- Startup: Load model, generate embeddings, store in pgvector
- Query: Embed query, vector similarity search (pgvector's `<->` operator)
- **Pros:** Semantic search, better quality
- **Cons:** Slower startup (model loading), requires GPU for large scale

**Chunking Strategy:**
```python
chunk_size = 800  # characters, ~200 tokens
overlap = 100     # prevent context loss at boundaries
```

**Metadata Tracking:**
- `parent_id`: Links chunks to original document
- `meta`: Source URL, author, timestamp (for citations)
- `chunk_index`: Enables ordered retrieval

**Example: Confluence Page → RAG**
```
1. Fetch page content via API
2. Chunk into 800-char segments with 100-char overlap
3. Generate embeddings (if vector mode)
4. Store in pgvector with metadata
5. Index for search
```

### 5.5 Slack Integration Architecture

**Command Routing:**
```
/em-agent triage        → Generate triage report (stale PRs, open incidents)
/em-agent approvals     → List pending approvals with interactive buttons
/em-agent ask <query>   → RAG search, post answer
/em-agent standup       → Daily standup summary (blockers, achievements)
```

**Interactive Workflows:**
1. **Approval Buttons**
   - Slack Block Kit buttons with `action_id`
   - Click → POST to `/v1/slack/interactions`
   - Update approval record → enqueue job → update Slack message

2. **Rich Reports**
   - Block Kit sections, dividers, context blocks
   - Color-coded (green = healthy, red = at-risk)
   - Threaded replies for details

**Security:**
- HMAC signature verification (Slack signing secret)
- Timestamp validation (prevent replay attacks)
- User identity mapping (Slack user ID → email → internal user)

### 5.6 Event Bus (NATS) Patterns

**Publisher-Subscriber Topics:**

1. **`events.github`**: Raw GitHub webhook events
   - Subscribers: metrics aggregator, notification service
   - Enables future ML feature engineering

2. **`signals.evaluated`**: Policy evaluation results
   - Subscribers: alerting, audit log
   - Schema: `{signal_type, severity, subject, timestamp}`

3. **`approvals.requested`**: Manual approval needed
   - Subscribers: Slack notifier, email service (future)
   - Enables multi-channel notifications

**Design Benefits:**
- Decoupling: Gateway doesn't know about all consumers
- Scalability: Add new subscribers without changing publisher
- Reliability: JetStream persistence ensures no event loss

---

## 6. Data Flow & Integration Patterns

### 6.1 Webhook Ingestion Flow

**GitHub PR Opened:**
```
1. GitHub webhook → POST /webhooks/github
2. Validate HMAC signature
3. Store in events_raw (idempotent via delivery_id)
4. Publish to NATS events.github topic
5. Celery worker: Update PR metadata cache
6. dbt incremental run: Compute WIP metrics
7. If signal triggered (WIP > limit): Send Slack alert
```

**Key Design Choices:**
- **Idempotency:** `delivery_id` prevents duplicate processing
- **Async Processing:** Webhook responds in <100ms, work happens in background
- **Separation of Concerns:** Webhook handler doesn't know about downstream consumers

### 6.2 Signal Evaluation Flow

**Policy Engine Pattern:**

```
1. Periodic job (every 60s): Run signal evaluator
2. Load rules from YAML: {name, kind, parameters}
3. For each rule:
   a. Query database (e.g., "PRs older than 48h")
   b. Evaluate policy (OPA or internal logic)
   c. Determine action (notify, block, auto-approve)
4. Create approval record if manual action needed
5. Publish signal.evaluated event
6. Slack notification for HITL workflows
```

**Example Rule (YAML):**
```yaml
- name: stale_pr
  kind: stale_pr
  older_than_hours: 48
  action: notify  # or 'block', 'auto-approve'
```

### 6.3 Approval Workflow

**Human-in-the-Loop Pattern:**

```
1. Action requires approval (e.g., "close stale PR")
2. Create approval record (status: pending)
3. Send Slack message with buttons: [Approve] [Reject]
4. User clicks button
5. Slack interaction → POST /v1/slack/interactions
6. Update approval (status: approved, decided_by: user)
7. Enqueue workflow_job in Celery
8. Worker executes action (e.g., POST to GitHub API)
9. Update job (status: completed)
10. Update Slack message (green checkmark)
```

**Temporal Long-Running Variant:**
```
1. Start Temporal workflow ("deploy if no incidents in 48h")
2. Wait 48 hours (durable, survives restarts)
3. Query incidents table
4. If none: Auto-approve deploy
5. If exists: Request manual approval
6. Complete workflow
```

---

## 7. Observability & Operations

### 7.1 Logging Strategy

**Structured Logging:**
```python
logger.info(
    "approval.created",
    approval_id=123,
    user_id=456,
    action="deploy",
    duration_ms=50
)
```

**Benefits:**
- Machine-parseable (JSON)
- Searchable in log aggregators (Datadog, Splunk)
- Correlation IDs for tracing requests

**Secret Redaction:**
- Regex patterns remove `Authorization`, `Bearer`, `password` from logs
- Prevents accidental credential leakage

### 7.2 Metrics (Prometheus)

**Application Metrics:**
```python
approvals_decisions_total.labels(status="approve").inc()
approvals_latency_seconds.observe(0.45)
workflows_auto_vs_hitl_total.labels(mode="auto").inc()
```

**Infrastructure Metrics:**
- Request rate, latency, error rate (RED method)
- Database connection pool usage
- Celery queue depth

**Alerting Examples:**
- P95 latency > 1s: Performance degradation
- Error rate > 5%: Investigate failures
- Queue depth > 1000: Worker scaling needed

### 7.3 Tracing (OpenTelemetry)

**Distributed Tracing:**
```
Webhook Request (trace_id: abc123)
  ├─ DB Insert: events_raw (50ms)
  ├─ NATS Publish (5ms)
  └─ Celery Enqueue (10ms)
     └─ Worker: Send Slack (200ms)
```

**Benefits:**
- Identify slow database queries
- Find network latency bottlenecks
- Debug complex multi-service flows

---

## 8. Security & Compliance

### 8.1 Authentication & Authorization

**API Authentication:**
- JWT tokens (Bearer scheme)
- Payload: `{user_id, email, exp, scopes}`
- Validation: Signature, expiration, scopes

**Slack Verification:**
- HMAC-SHA256 signature validation
- Timestamp check (prevent replay > 5 min old)
- Secret rotation support

**Authorization Model:**
- Role-based access control (RBAC) foundation
- Scopes: `approvals:write`, `metrics:read`, `admin:*`
- Future: Attribute-based (team membership, project ownership)

### 8.2 Data Privacy

**PII Handling:**
- Email hashing for identity mapping
- No storage of Slack message content (only metadata)
- Soft deletes preserve audit trail

**Secret Management:**
- Environment variables (12-factor app)
- Support for Vault/AWS Secrets Manager
- Never log secrets (redaction middleware)

### 8.3 Compliance Considerations

**Audit Trail:**
- All approvals recorded with `decided_by`, `decided_at`, `reason`
- Immutable events_raw table
- Deletion logs (soft delete timestamps)

**Data Retention:**
- Configurable retention (default: 30 days)
- Automated purge jobs for old events
- Export API for compliance reporting

---

## 9. Testing Strategy

### 9.1 Test Pyramid

**Unit Tests (60%):**
- Models, schemas, utilities
- Mock external dependencies (database, APIs)
- Fast (<1s total), run on every commit

**Integration Tests (30%):**
- API endpoints with real database (test DB)
- Celery task execution (eager mode)
- End-to-end flows (webhook → processing → result)

**Smoke Tests (10%):**
- Gateway health check in Docker Compose
- RAG service startup and search
- Database migrations apply cleanly

**Current Coverage: 88%**
- Core business logic: >90%
- Infrastructure code: >70%
- UI/presentation: >50%

### 9.2 Testing Patterns

**Fixtures (conftest.py):**
```python
@pytest.fixture
def db_session():
    """Provide isolated test database session"""
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
```

**Factory Pattern:**
```python
def create_approval(**kwargs):
    defaults = {"status": "pending", "action": "deploy"}
    return Approval(**{**defaults, **kwargs})
```

**Mock External Services:**
```python
@patch('httpx.Client.post')
def test_slack_notification(mock_post):
    mock_post.return_value.status_code = 200
    result = send_slack_message("test")
    assert result["ok"] is True
```

---

## 10. Deployment Architecture

### 10.1 Local Development (Docker Compose)

**Services:**
```yaml
services:
  db: postgres:15 + pgvector
  redis: redis:7-alpine
  nats: nats:2.10
  gateway: FastAPI app
  rag: RAG service
  workers: Celery workers
  temporal: Temporal server
  ui: Flask admin
```

**Development Workflow:**
```bash
make up      # Start all services
make logs    # Follow logs
make test    # Run test suite
make down    # Cleanup
```

### 10.2 Production Deployment (Kubernetes)

**Deployment Strategy:**
- **Gateway**: Horizontal pod autoscaling (2-10 replicas)
- **Workers**: Separate deployment, KEDA autoscaling (queue depth)
- **Database**: Managed PostgreSQL (RDS, Cloud SQL)
- **Redis**: Managed Redis (ElastiCache, Memorystore)
- **NATS**: StatefulSet with JetStream persistence

**Ingress:**
- NGINX ingress controller
- TLS termination (Let's Encrypt)
- Rate limiting (per-IP, per-user)

**Configuration:**
- Kubernetes ConfigMaps (non-secret config)
- Kubernetes Secrets (database passwords, API keys)
- Environment-specific overlays (Kustomize)

### 10.3 CI/CD Pipeline

**GitHub Actions Workflow:**
1. **Linting**: ruff, black, mypy
2. **Tests**: pytest with coverage
3. **Build**: Docker images (multi-stage builds)
4. **Push**: Container registry (GHCR, ECR)
5. **Deploy**: kubectl apply (staging first, then prod)

**Deployment Gates:**
- Code review required
- Tests must pass
- Coverage > 80%
- Security scan (Snyk, Trivy)

---

## 11. Trade-offs & Alternatives Considered

### 11.1 Language Choice: Python vs. Go/Rust

**Considered:** Go for performance, Rust for safety

**Chose Python because:**
- **Data Science Alignment**: ML/AI features require Python anyway
- **Developer Velocity**: Faster iteration in product discovery phase
- **Ecosystem**: Rich data processing libraries (pandas, sklearn, dbt)
- **Hiring**: Larger talent pool, easier onboarding

**Trade-off:** Lower raw performance, but I/O-bound workload mitigates this.

### 11.2 Database: PostgreSQL vs. ClickHouse/Snowflake

**Considered:** ClickHouse for analytics, Snowflake for data warehouse

**Chose PostgreSQL because:**
- **Simplicity**: Single database reduces operational complexity
- **Cost**: No per-query charges (Snowflake) or cluster management (ClickHouse)
- **Sufficient Scale**: <10M events/day fits comfortably
- **Flexibility**: JSONB + CTEs handle complex analytics

**Future:** May add ClickHouse for >100M events/day scale.

### 11.3 RAG: Custom vs. LangChain

**Considered:** LangChain for rapid development

**Chose Custom because:**
- **Control**: Exact chunking, indexing, retrieval logic
- **Performance**: No framework overhead
- **Cost**: TF-IDF baseline is free (vs. always using embeddings)
- **Simplicity**: <500 lines vs. complex framework

**Trade-off:** Less community support, but requirements are simple.

### 11.4 Frontend: React vs. Flask Templates

**Considered:** React for richer UX

**Chose Flask Templates because:**
- **Speed**: Faster to build admin dashboards
- **Complexity**: Avoid frontend build process, state management
- **Team**: Backend engineers can ship UI without frontend expertise
- **Use Case**: Admin UI, not customer-facing product

**Future:** May add React for customer-facing features.

---

## 12. Scaling & Performance Considerations

### 12.1 Current Scale Targets

- **Events**: 10K-100K events/day
- **Users**: 50-500 engineers
- **API Requests**: 1K-10K req/min
- **RAG Documents**: 1K-10K documents

### 12.2 Bottlenecks & Solutions

**Database:**
- **Bottleneck:** Complex DORA metric queries (multi-table joins)
- **Solution:** Materialized views, pre-computed aggregates
- **Future:** Partition events_raw by month

**Workers:**
- **Bottleneck:** Slack notifications during incident storms
- **Solution:** Rate limiting, batch notifications
- **Future:** Priority queues (P0 incidents first)

**RAG:**
- **Bottleneck:** Embedding generation for large documents
- **Solution:** Background indexing, incremental updates
- **Future:** GPU-accelerated embeddings

### 12.3 Horizontal Scaling Strategy

**Stateless Services (Gateway, RAG):**
- Add more pods/instances
- Load balancer distributes traffic
- No shared state (session in Redis)

**Stateful Services (Workers, Database):**
- Workers: Add more workers (Celery scales linearly)
- Database: Read replicas for analytics queries
- NATS: Clustered mode for high availability

---

## 13. Future Roadmap & Evolution

### 13.1 Short-Term (3-6 months)

1. **Advanced Metrics**
   - Flow efficiency (active time / total time)
   - Code review bottleneck analysis
   - Team velocity trends

2. **Slack Enhancements**
   - Modals for complex forms
   - Scheduled reports (daily standup, weekly retro)
   - Interactive dashboards (charts in Slack)

3. **ML Features (Phase 8)**
   - Anomaly detection (unusual deploy patterns)
   - PR merge time prediction
   - Smart triage recommendations

### 13.2 Medium-Term (6-12 months)

1. **Multi-Tenancy**
   - Organization isolation
   - Per-team configuration
   - Usage-based billing foundations

2. **Advanced Workflows**
   - Deployment pipelines (progressive rollout)
   - Incident response playbooks
   - Onboarding automation

3. **Integrations**
   - PagerDuty, Datadog, Sentry
   - GitLab, Bitbucket support
   - Jira Service Management

### 13.3 Long-Term Vision (12+ months)

1. **AI-Powered Insights**
   - LLM-generated summaries (GPT-4, Claude)
   - Root cause analysis
   - Predictive alerting

2. **Collaboration Features**
   - Shared dashboards
   - Comments and annotations
   - Team health scoring

3. **Enterprise Features**
   - SSO/SAML integration
   - Advanced RBAC (team-based, project-based)
   - Compliance reporting (SOC2, GDPR)

---

## Conclusion: Principles for Future Decisions

As EM Agent evolves, these principles guide architecture decisions:

1. **Human-Centered Design**: Automation assists, never replaces human judgment
2. **Progressive Complexity**: Start simple (TF-IDF), add sophistication as needed (embeddings)
3. **Operational Simplicity**: Prefer managed services, minimize moving parts
4. **Data as Asset**: Event sourcing enables future features without re-ingestion
5. **Composability**: Loosely-coupled services enable independent evolution
6. **Observability First**: Instrument before deploying, monitor continuously
7. **Cost-Conscious**: Free/cheap defaults (TF-IDF, PostgreSQL), premium options available

**The North Star:** Build a platform that **engineering teams trust** to automate toil while keeping humans in control of critical decisions.

---

## Appendix: Key Metrics & SLOs

**Service Level Objectives:**

| Metric | Target | Rationale |
|--------|--------|-----------|
| API P95 Latency | <500ms | Interactive Slack commands feel instant |
| Webhook Processing | <100ms | GitHub expects quick response |
| Test Coverage | >80% | Confidence in refactoring |
| Deployment Frequency | >10/day | Fast iteration, small changes |
| MTTR | <1 hour | Quick recovery from incidents |
| Uptime | >99.5% | ~3.6h downtime/month acceptable |

**Capacity Planning:**

| Resource | Current | 10x Scale | 100x Scale |
|----------|---------|-----------|------------|
| Database | 50GB | 500GB | 5TB (partition) |
| Redis | 1GB | 10GB | 100GB (cluster) |
| Workers | 4 | 40 | 400 (auto-scale) |
| API Pods | 2 | 20 | 200 (HPA) |

---

**Version:** 1.0
**Last Updated:** 2025-11-08
**Author:** Evan Hourigan
**Status:** Living Document (update as architecture evolves)
