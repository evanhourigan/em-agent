# Phase 7 Plan - Agent Evolution Roadmap

**Status:** Plan approved, ready to execute
**Date Created:** 2025-11-25
**Est. Total Time:** 8-10 weeks

---

## Executive Summary

Transform EM Agent from a **data aggregation platform** (v1.x) into an **intelligent agent platform** (v2.0) through 4 iterative releases. Each release delivers production value while building toward the vision of LLM-powered agent orchestration.

### Current State (v1.0.0)
- ✅ 18 integrations operational
- ✅ Complete DORA metrics suite
- ✅ Production-ready infrastructure
- ⚠️ Phase 7 features are CRUD prototypes (no intelligence/automation)
- ⚠️ Agent router uses naive string matching (no LLM)

### Target State (v2.0.0)
- 🎯 21+ integrations
- 🎯 Intelligent Incident Co-pilot (auto-triage, runbook suggestions)
- 🎯 Integrated systems (OKRs ← DORA metrics, Slack everywhere)
- 🎯 LLM-powered multi-agent architecture with sub-agents
- 🎯 Conversational AI that orchestrates complex workflows

---

## Release Roadmap

### v1.1.0 - Complete Integrations (3-5 days) 📊

**Goal:** Reach 21 integrations total, complete data coverage

#### Tasks
1. **Implement New Relic webhook handler**
   - Path: `/webhooks/newrelic`
   - Events: APM events, deployment markers, alert notifications
   - Pattern: Follow Datadog/Sentry implementation
   - File: `services/gateway/app/api/v1/routers/webhooks.py`
   - ~150 lines

2. **Implement Prometheus webhook handler**
   - Path: `/webhooks/prometheus`
   - Events: Alertmanager webhook format (alerts firing/resolved)
   - Integration with Prometheus Alertmanager
   - ~150 lines

3. **Implement CloudWatch webhook handler**
   - Path: `/webhooks/cloudwatch`
   - Events: SNS topic format for CloudWatch alarms
   - EventBridge integration for AWS events
   - ~150 lines

4. **Update configuration**
   - Feature flags already exist in `config.py` (lines 80-82)
   - Just need to keep them enabled
   - Update README.md with new integrations
   - Update API_REFERENCE.md

5. **Testing**
   - Add webhook tests for each integration
   - Follow pattern from existing webhook tests
   - Verify idempotency with delivery_id

6. **Documentation**
   - Update README.md integrations list
   - Add webhook examples to API_REFERENCE.md
   - Update CHANGELOG.md

#### Deliverables
- ✅ 3 new webhook handlers (New Relic, Prometheus, CloudWatch)
- ✅ Tests for each integration
- ✅ Documentation updates
- ✅ CI passing
- ✅ Commit and tag v1.1.0

#### Technical Notes
**Existing Infrastructure:**
- Feature flags: `integrations_newrelic_enabled`, `integrations_prometheus_enabled`, `integrations_cloudwatch_enabled`
- Database: `events_raw` table with comprehensive indexes
- Event bus: NATS publish pattern already established
- Pattern to follow: See Datadog handler at webhooks.py:565-634

---

### v1.2.0 - Intelligent Incident Co-pilot (2-3 weeks, iterative) 🤖

**Goal:** Transform CRUD incident tracker into AI-powered co-pilot

#### Current State Analysis
**What exists:**
- Basic incident CRUD API (`/v1/incidents`)
- Database tables: `incidents`, `incident_timeline`
- Endpoints: create, add note, close, update severity
- **Location:** `services/gateway/app/api/v1/routers/incidents.py`

**What's missing:**
- ❌ No integration with PagerDuty/Sentry webhooks
- ❌ No LLM/AI for analysis
- ❌ No automated triage
- ❌ No runbook suggestions
- ❌ No Slack notifications

#### Phase 1: Auto-Creation (Week 1)

**Tasks:**
1. **Wire PagerDuty webhook to incidents**
   - Update `webhooks.py` PagerDuty handler (line 427)
   - When `incident.triggered` event received, create incident record
   - Extract: title, severity from PagerDuty payload
   - Add `external_id` field to incidents table for deduplication

2. **Wire Sentry webhook to incidents**
   - Update `webhooks.py` Sentry handler (line 651)
   - When `issue.created` with high priority, create incident
   - Map Sentry severity → incident severity

3. **Wire Datadog webhook to incidents**
   - Update `webhooks.py` Datadog handler (line 565)
   - When monitor alert with priority="critical", create incident
   - Extract metric context

4. **Add deduplication logic**
   - Check if incident already exists by external_id
   - Update existing incident instead of creating duplicate
   - Add timeline entry for duplicate events

5. **Testing**
   - Trigger PagerDuty webhook → verify incident created
   - Trigger Sentry error → verify incident created
   - Trigger Datadog alert → verify incident created

**Deliverables:**
- Auto-incident creation from 3 webhook sources
- Deduplication preventing duplicate incidents
- Timeline tracking all related events

#### Phase 2: Intelligence (Week 2)

**Tasks:**
1. **Build pluggable LLM client**
   - Create `services/gateway/app/services/llm_client.py`
   - Support both Claude (Anthropic) and OpenAI
   - Use existing config: `openai_api_key`, `openai_model`
   - Add new config: `anthropic_api_key`, `llm_provider` (openai|anthropic)
   - Interface: `generate(prompt: str, tools: list) -> dict`

2. **Implement severity assessment agent**
   - New function: `assess_incident_severity(incident_data: dict) -> str`
   - Prompt: Analyze error message, affected service, time, suggest severity
   - Tool: Query past incidents with similar characteristics
   - Return: low|medium|high|critical with reasoning

3. **Add RAG integration for runbook retrieval**
   - Connect to existing RAG service (port 8001)
   - New function: `suggest_runbooks(incident: Incident) -> list[dict]`
   - Search RAG with: error type, service name, keywords
   - Return: Top 3 relevant runbooks with snippets

4. **Implement triage agent**
   - New function: `triage_incident(incident: Incident) -> dict`
   - Combines: severity assessment + runbook search + past incidents
   - Prompt: "What are the most likely causes and next steps?"
   - Tool access: RAG, metrics API, past incident DB
   - Return: {likely_causes, suggested_actions, relevant_runbooks}

5. **Update incident API**
   - Add GET `/v1/incidents/{id}/suggestions` endpoint
   - Calls triage agent on-demand
   - Cache suggestions to avoid redundant LLM calls

**Deliverables:**
- Pluggable LLM client (Claude + OpenAI support)
- Severity assessment with AI reasoning
- RAG-based runbook suggestions
- Triage agent providing actionable insights

#### Phase 3: Integration (Week 3)

**Tasks:**
1. **Add Slack notifications**
   - Update `services/gateway/app/services/slack_client.py`
   - New method: `post_incident_notification(incident, suggestions)`
   - Rich formatting with:
     - Incident title, severity, timestamp
     - AI-suggested actions
     - Relevant runbooks (links if available)
     - Button: "View in Dashboard" or "I'm investigating"
   - Send to configurable channel (default: `#incidents`)

2. **Build post-mortem draft generator**
   - New endpoint: POST `/v1/incidents/{id}/generate-postmortem`
   - LLM prompt: Convert incident timeline into structured post-mortem
   - Sections: Summary, Timeline, Root Cause, Impact, Action Items
   - Return: Markdown document ready for review

3. **Add incident similarity search**
   - New endpoint: GET `/v1/incidents/{id}/similar`
   - Use vector embeddings of incident descriptions
   - Query past incidents with cosine similarity
   - Return: Top 5 similar incidents with resolutions

4. **Polish error handling**
   - Graceful degradation if LLM unavailable
   - Timeouts for LLM calls (max 30s)
   - Retry logic with exponential backoff
   - Fallback to basic incident creation if AI fails

5. **End-to-end testing**
   - Trigger PagerDuty incident
   - Verify: auto-creation, AI triage, Slack notification
   - Generate post-mortem
   - Find similar incidents

**Deliverables:**
- Slack integration for incident notifications
- AI-generated post-mortem drafts
- Similarity search for past incidents
- Robust error handling and fallbacks
- **Commit and tag v1.2.0**

#### Technical Decisions
- **LLM Provider:** Pluggable (Claude + OpenAI)
- **RAG:** Use existing service at port 8001
- **Embeddings:** Sentence-transformers (already in RAG service)
- **Storage:** PostgreSQL (no new databases)
- **Async:** Use `asyncio.create_task()` for non-blocking LLM calls

---

### v1.3.0 - Connect Everything (1-2 weeks) 🔗

**Goal:** Wire disparate systems together, demonstrate data flows

#### Current State Analysis
**Disconnected systems:**
- OKRs exist but don't connect to DORA metrics
- Onboarding exists but no Slack integration
- No attribution model (which work contributed to which OKRs)
- Slack only used for deployment notifications

#### Tasks

**1. OKR → DORA Metrics Connection**

Create API to link key results to metrics:
```python
# New endpoint
POST /v1/okr/krs/{id}/metrics
{
  "metric_type": "deployment_frequency",  # or lead_time, cfr, mttr
  "target_value": 10,  # 10 deployments per day
  "mapping": "sum"  # sum, avg, min, max
}
```

Background job:
- Query DORA metrics daily
- Update linked OKR progress automatically
- Post to Slack when OKR milestone hit (50%, 75%, 100%)

**2. Onboarding → Slack Integration**

- When task assigned: Send Slack DM to assignee
- 2 days before due date: Send reminder
- When completed: Send celebration message
- Weekly digest: "3 tasks due this week"

New methods in `slack_client.py`:
- `send_task_assignment(user_id, task)`
- `send_task_reminder(user_id, task)`
- `send_task_completion(user_id, task)`

**3. Attribution Model**

Create mapping:
```
PR #123 (merged) → Deployment ABC → OKR "Reduce deploy time" → Objective "Ship faster"
```

New table: `okr_contributions`
- id, okr_kr_id, event_type (pr, deployment, incident), event_id, impact (float), created_at

New endpoint: GET `/v1/okr/objectives/{id}/contributors`
- Returns: Top engineers contributing to objective
- Based on: PRs merged, deployments shipped, incidents resolved

**4. Cross-Feature Notifications**

Slack notifications for:
- New incidents created (already in v1.2.0)
- OKR milestones reached (25%, 50%, 75%, 100%)
- Onboarding tasks overdue
- DORA metrics anomalies (deploy freq drops 50%)

Daily digest option:
- Summary of yesterday's activity
- Incidents opened/closed
- OKR progress
- DORA trends (up/down arrows)

**5. Simple Dashboard**

Create HTML page showing connections:
```
/dashboard
```

Visualize:
- Events flowing in (last 100)
- DORA metrics current values
- OKRs with progress bars
- Incidents by status
- Network graph: Events → Metrics → OKRs

Use simple HTML + Chart.js (no React/Vue overhead)

#### Deliverables
- ✅ Automated OKR progress from DORA metrics
- ✅ Slack integration for onboarding tasks
- ✅ Attribution model (PRs → OKRs)
- ✅ Cross-feature Slack notifications
- ✅ Simple dashboard showing data flows
- ✅ **Commit and tag v1.3.0**

---

### v2.0.0 - Agentic Infrastructure (MAJOR RELEASE, 3-4 weeks) 🧠

**Goal:** Transform into LLM-powered multi-agent orchestration platform

#### Why Major Release?

**Breaking Changes:**
- New `/v2/agent/chat` endpoint (preserve `/v1/agent/run` for compatibility)
- Conversational API requires session management
- Sub-agent architecture changes internal routing
- Temporal workflows become required (currently optional)

**New Dependencies:**
- `anthropic` SDK for Claude
- `openai` SDK for GPT-4
- Temporal server (required, not optional)
- Redis for conversation history (or PostgreSQL JSONB)

**Conceptual Shift:**
- **v1.x:** Data aggregation platform (collect, calculate, automate)
- **v2.0:** Intelligent agent platform (reason, orchestrate, recommend)

Like the difference between:
- GitHub (hosting) vs GitHub Copilot (AI assistant)
- Jira (tracking) vs Jira Intelligence (predictions)

#### Phase 1: Core Infrastructure (Week 1)

**1. Create new agent endpoint**

File: `services/gateway/app/api/v2/routers/agent.py` (new v2 router)

```python
@router.post("/chat")
async def agent_chat(
    request: AgentChatRequest,  # {session_id, message, context}
    session: Session = Depends(get_db_session),
) -> AgentChatResponse:  # {response, tools_used, thinking}
    """
    Conversational AI agent with multi-turn memory.

    Supports tool-calling for dynamic orchestration.
    """
```

**2. Build pluggable LLM abstraction**

File: `services/gateway/app/services/llm_client.py` (extend from v1.2.0)

```python
class LLMClient(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[Tool],
        **kwargs
    ) -> ChatResponse:
        pass

class ClaudeClient(LLMClient):
    # Uses Anthropic SDK, Claude 3.5 Sonnet

class OpenAIClient(LLMClient):
    # Uses OpenAI SDK, GPT-4o
```

**3. Implement tool-calling protocol**

File: `services/gateway/app/core/tools.py` (new)

```python
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable

# Register tools
TOOL_REGISTRY = {
    "query_dora_metrics": query_dora_metrics_tool,
    "search_runbooks": search_runbooks_tool,
    "create_incident": create_incident_tool,
    "list_open_prs": list_open_prs_tool,
    # ... etc
}
```

**4. Add conversation memory**

New table: `agent_conversations`
- id, session_id, user_id (optional), created_at, updated_at

New table: `agent_messages`
- id, conversation_id, role (user/assistant/system), content (JSONB), created_at

Retrieve last N messages for context in multi-turn conversations.

**5. Testing**

Test: Basic conversation with 2-3 tools
```
User: "Show me deployment frequency for last week"
Agent: [calls query_dora_metrics tool]
Agent: "Here are your deployments..."
User: "Which team has the lowest?"
Agent: [remembers context, queries by team]
```

#### Phase 2: Sub-Agent Architecture (Week 2)

**1. Define agent interface**

File: `services/gateway/app/agents/base.py` (new)

```python
@dataclass
class Agent:
    name: str
    description: str  # For coordinator to choose when to invoke
    system_prompt: str
    tools: list[Tool]
    llm_config: dict  # model, temperature, etc.

    async def invoke(self, query: str, context: dict) -> AgentResponse:
        """Execute agent with given query and context."""
```

**2. Implement specialized agents**

**Metrics Agent** (`agents/metrics_agent.py`):
- System prompt: "You analyze engineering metrics and provide insights..."
- Tools: query_dora_metrics, query_code_quality, compare_teams
- Use case: "How's our deployment frequency trending?"

**Incident Agent** (`agents/incident_agent.py`):
- System prompt: "You help triage and resolve incidents..."
- Tools: create_incident, search_similar_incidents, suggest_runbooks
- Use case: "Production is down, help me triage"

**Review Agent** (`agents/review_agent.py`):
- System prompt: "You help with code reviews and PR management..."
- Tools: list_open_prs, assign_reviewer, draft_pr_comment
- Use case: "Find PRs that need review and assign reviewers"

**OKR Agent** (`agents/okr_agent.py`):
- System prompt: "You help track and manage objectives..."
- Tools: list_okrs, update_progress, suggest_action_items
- Use case: "Show me OKRs behind schedule"

**3. Build coordinator agent**

File: `agents/coordinator.py`

```python
class CoordinatorAgent:
    """
    Routes user queries to appropriate sub-agents.

    Uses LLM to determine which agent(s) to invoke.
    Can invoke multiple agents in parallel or sequence.
    """

    async def route(self, query: str) -> list[Agent]:
        # LLM decides: "This query needs Metrics Agent + OKR Agent"
        pass

    async def orchestrate(self, query: str) -> str:
        agents = await self.route(query)
        results = await asyncio.gather(*[
            agent.invoke(query, context={})
            for agent in agents
        ])
        # Synthesize results from multiple agents
        return self.synthesize(results)
```

**4. Add agent registry**

File: `agents/__init__.py`

```python
AGENT_REGISTRY = {
    "metrics": MetricsAgent(),
    "incident": IncidentAgent(),
    "review": ReviewAgent(),
    "okr": OKRAgent(),
}

def get_agent(name: str) -> Agent:
    return AGENT_REGISTRY[name]
```

#### Phase 3: Temporal Integration (Week 3)

**Why Temporal?**
- Long-running workflows (onboarding spans weeks)
- Reliable execution with retries
- Saga patterns for complex multi-step tasks
- Human-in-loop approvals
- Compensation logic (rollback on failure)

**1. Integrate Temporal into agent execution**

File: `services/gateway/app/services/temporal_workflows.py` (expand existing)

```python
@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, task: AgentTask) -> WorkflowResult:
        # Execute multi-step agent task
        # Can pause for human approval
        # Can retry individual steps
        # Can compensate on failure
```

**2. Build saga patterns**

Example: "Onboard new engineer"
```
Step 1: Create onboarding plan → [Agent generates tasks]
Step 2: Provision GitHub access → [Activity: call GitHub API]
Step 3: Add to Slack channels → [Activity: call Slack API]
Step 4: Schedule 1:1s → [Activity: call calendar API]
Step 5: Send welcome message → [Activity: send email]

If Step 3 fails: Compensate by revoking GitHub access
```

**3. Add compensation logic**

```python
@activity.defn
async def provision_github_access(user: str):
    # Add user to org

@activity.defn
async def revoke_github_access(user: str):
    # Compensation: remove user from org
```

**4. Implement long-running agent tasks**

Use case: "Optimize deployment process"
- Week 1: Agent analyzes current deploy times
- Week 2: Agent proposes optimizations
- Week 3: (Human approval)
- Week 4: Agent implements changes
- Week 5: Agent monitors impact

Temporal workflow runs for weeks, can be queried for status.

#### Phase 4: Migration & Polish (Week 4)

**1. Migrate Incident Co-pilot to new architecture**

Replace ad-hoc LLM calls in v1.2.0 with:
- IncidentAgent from agent registry
- Conversation memory for incident discussions
- Tool-calling for runbook search, similar incidents

**2. Migrate existing agent.py routes**

Convert `/v1/agent/run` simple routes to sub-agents:
- "sprint health" → MetricsAgent
- "stale PRs" → ReviewAgent
- "missing tickets" → ReviewAgent

**3. Add comprehensive agent tests**

Test suite:
- Unit tests for each agent
- Integration tests for coordinator
- End-to-end tests for workflows
- Load testing (100 concurrent agent requests)

**4. Performance optimization**

- Cache LLM responses (same query within 5 min)
- Batch tool calls where possible
- Stream LLM responses (don't wait for completion)
- Parallel agent invocation

**5. Security review**

- Prompt injection protection (sanitize user input)
- Tool access control (agents can't access admin tools)
- Audit logging (all agent actions logged)
- Rate limiting (per user, per agent)

**6. Documentation**

New docs:
- `docs/AGENT_ARCHITECTURE.md` - How agents work
- `docs/AGENT_DEVELOPMENT.md` - How to build new agents
- `docs/AGENT_API.md` - `/v2/agent/chat` API reference
- `docs/MIGRATION_V1_TO_V2.md` - Upgrade guide

#### Deliverables
- ✅ `/v2/agent/chat` conversational endpoint
- ✅ Pluggable LLM client (Claude + OpenAI)
- ✅ 4+ specialized sub-agents
- ✅ Coordinator agent with routing
- ✅ Tool-calling protocol
- ✅ Conversation memory
- ✅ Temporal workflow integration
- ✅ Agent registry and discovery
- ✅ Comprehensive tests and docs
- ✅ Migration of v1.2.0 Incident Co-pilot
- ✅ Security review complete
- ✅ **Commit and tag v2.0.0 - "AGENTIC PLATFORM"**

---

## Timeline Summary

| Release | Duration | Deliverable |
|---------|----------|-------------|
| v1.1.0 | 3-5 days | 21 integrations (New Relic, Prometheus, CloudWatch) |
| v1.2.0 | 2-3 weeks | Intelligent Incident Co-pilot (AI triage, runbooks) |
| v1.3.0 | 1-2 weeks | Connected systems (OKRs←DORA, Slack everywhere) |
| v2.0.0 | 3-4 weeks | Agentic infrastructure (LLM orchestration, sub-agents) |

**Total:** ~8-10 weeks to full agentic platform

---

## Success Metrics

### v1.1.0 Success
- [ ] All 3 new webhooks passing tests
- [ ] CI green
- [ ] Documentation updated
- [ ] Real webhook events processed successfully

### v1.2.0 Success
- [ ] Incidents auto-created from PagerDuty/Sentry/Datadog
- [ ] AI severity assessment accuracy >80%
- [ ] Runbook suggestions relevant (manual eval)
- [ ] Slack notifications delivered within 30s
- [ ] Post-mortem generation saves >1 hour per incident

### v1.3.0 Success
- [ ] OKR progress auto-updates daily from DORA metrics
- [ ] Slack reminders reduce task overdue rate by 50%
- [ ] Attribution model shows top 10 contributors per objective
- [ ] Dashboard loads in <2s with real data

### v2.0.0 Success
- [ ] Agent conversation maintains context over 5+ turns
- [ ] Sub-agents invoked correctly for 10 test scenarios
- [ ] Temporal workflows execute reliably (99.9% success)
- [ ] Agent response time <5s for simple queries
- [ ] Security review passes with 0 critical vulnerabilities
- [ ] 10+ agents built using the framework

---

## Technical Architecture Evolution

### v1.0.0 Architecture (Current)
```
Webhooks → events_raw → dbt → DORA Metrics
                      ↓
                    NATS → (future workers)

Basic agent.py with string matching
```

### v2.0.0 Architecture (Target)
```
Webhooks → events_raw → dbt → DORA Metrics
                      ↓              ↓
                    NATS    →   Agents (LLM-powered)
                                    ↓
                          [Coordinator Agent]
                          /      |      \
                    [Metrics] [Incident] [Review] [OKR]
                        ↓        ↓         ↓       ↓
                    [Tools: RAG, DB, APIs, Temporal]
                                    ↓
                          Human approvals (HITL)
                                    ↓
                          Execute actions
```

---

## Dependencies & Prerequisites

### v1.1.0 Prerequisites
- Current v1.0.0 codebase
- Test accounts: New Relic, Prometheus, AWS (for CloudWatch)

### v1.2.0 Prerequisites
- Python packages: `anthropic`, `openai` (or reuse existing)
- LLM API keys (Claude or OpenAI)
- RAG service running (already exists at port 8001)
- Slack bot token with message permissions

### v1.3.0 Prerequisites
- Slack bot with DM permissions
- Chart.js for dashboard visualization

### v2.0.0 Prerequisites
- Temporal server (can run via Docker Compose)
- Redis for conversation caching (optional, can use PostgreSQL)
- LLM API quotas sufficient for multi-agent calls

---

## Risk Mitigation

### Risks

**LLM Reliability:**
- Risk: LLM API downtime breaks critical features
- Mitigation: Graceful degradation, fallback to rule-based logic

**LLM Costs:**
- Risk: Uncontrolled LLM calls → high bills
- Mitigation: Rate limiting, caching, token budgets

**Prompt Injection:**
- Risk: Malicious user input manipulates agent behavior
- Mitigation: Input sanitization, prompt templates, tool access control

**Temporal Complexity:**
- Risk: Workflow bugs hard to debug
- Mitigation: Comprehensive logging, replay testing, start simple

**Migration Complexity:**
- Risk: v2.0.0 breaks existing v1.x users
- Mitigation: Keep `/v1/*` endpoints, provide migration guide

### Contingency Plans

**If LLM costs too high:**
- Use smaller models (GPT-3.5, Claude Haiku)
- Implement aggressive caching
- Reduce context window size

**If Temporal too complex:**
- Start with simple Celery tasks
- Migrate to Temporal incrementally
- Use Temporal only for long-running workflows

**If timeline slips:**
- De-scope v2.0.0 (release without Temporal)
- Iterate: v2.0 (core), v2.1 (workflows), v2.2 (advanced features)

---

## Next Actions

### Immediate (When Ready to Start)
1. **Checkout new branch:** `git checkout -b feature/v1.1.0-complete-integrations`
2. **Read webhook patterns:** Review Datadog handler as template
3. **Set up test accounts:** New Relic, Prometheus Alertmanager, AWS SNS
4. **Start coding:** Implement New Relic webhook first (simplest)

### Before Starting v1.2.0
1. **Get LLM API keys:** Anthropic (Claude) and/or OpenAI
2. **Design incident schema changes:** Add `external_id` field
3. **Review RAG service:** Ensure it has runbook documents indexed
4. **Plan Slack permissions:** Bot needs channel posting + DM sending

### Before Starting v2.0.0
1. **Set up Temporal:** Run locally via Docker Compose
2. **Architecture review:** Review agent patterns (ReAct, Chain-of-Thought)
3. **Read Anthropic/OpenAI docs:** Tool-calling APIs
4. **Performance baseline:** Measure current response times

---

## References

### Code Locations
- **Webhooks:** `services/gateway/app/api/v1/routers/webhooks.py`
- **Incidents:** `services/gateway/app/api/v1/routers/incidents.py`
- **Agent:** `services/gateway/app/api/v1/routers/agent.py`
- **OKR:** `services/gateway/app/api/v1/routers/okr.py`
- **Config:** `services/gateway/app/core/config.py`
- **Slack:** `services/gateway/app/services/slack_client.py`
- **Temporal:** `services/gateway/app/services/temporal_client.py`

### Documentation
- **ROADMAP.md** - High-level roadmap
- **API_REFERENCE.md** - Complete API docs
- **DEPLOYMENT.md** - Production deployment guide
- **CHANGELOG.md** - Release history

### External Resources
- [Anthropic Claude API](https://docs.anthropic.com/)
- [OpenAI API](https://platform.openai.com/docs)
- [Temporal Docs](https://docs.temporal.io/)
- [ReAct Paper](https://arxiv.org/abs/2210.03629) - Reasoning + Acting pattern

---

## Questions & Decisions

### Decisions Made
- ✅ Use pluggable LLM client (Claude + OpenAI)
- ✅ Keep `/v1/*` endpoints for backward compatibility
- ✅ Use Temporal for long-running workflows
- ✅ Iterative approach (prototype → harden)
- ✅ v2.0.0 is separate major release

### Open Questions
- [ ] Which LLM model for production? (Sonnet 3.5 vs GPT-4o)
- [ ] How many concurrent agent sessions to support?
- [ ] Redis vs PostgreSQL for conversation memory?
- [ ] Should agents be able to invoke other agents directly?

---

**Status:** Plan approved, ready to execute when you return! 🚀

**First step:** Implement v1.1.0 (New Relic, Prometheus, CloudWatch webhooks)
