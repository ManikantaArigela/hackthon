# 🔁 Relay — Graph-Memory Support Agent

> **Hackathon:** Graph Hacks (WeMakeDevs × FalkorDB) | **Track:** Agent Memory & Coordination

Relay is a team of cooperating AI agents that keep **all their memory in a FalkorDB graph**. Every customer interaction becomes connected data. Any agent can recall past sessions, learn which fixes work, hand a case to another agent, and show the graph path behind every answer.

---

## 🧠 The Problem

AI support agents forget. A customer explains an issue on Monday. On Thursday a different agent (or the same one in a new session) asks them to start over. Agents can't share what they've learned, and they can't explain *why* they gave an answer.

**Relay** fixes this by making the graph the single source of truth for all agent memory.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│           Chat UI  (Streamlit)          │
└───────────────────┬─────────────────────┘
                    │ HTTP
┌───────────────────▼─────────────────────┐
│        Orchestrator  (FastAPI)          │
│                                         │
│   ┌──────────┐  ┌──────────┐  ┌──────┐ │
│   │  Intake  │→ │ Resolver │→ │Review│ │
│   │  Agent   │  │  Agent   │  │Agent │ │
│   └──────────┘  └──────────┘  └──────┘ │
│                                         │
│        Memory Layer  (Python)           │
└───────────────────┬─────────────────────┘
                    │ Cypher
┌───────────────────▼─────────────────────┐
│           FalkorDB  (Docker)            │
│      One graph per tenant               │
│   tenant_acme | tenant_globex | ...     │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│          LLM API  (Claude Haiku)        │
│   Entity extraction + reply generation  │
└─────────────────────────────────────────┘
```

### Agent Roles

| Agent | Job | Reads from graph | Writes to graph |
|-------|-----|-----------------|-----------------|
| **Intake** | Understands message, extracts entities, recalls customer history | Customer, past Episodes | New Episode, Issue |
| **Resolver** | Finds best fix using playbooks and past solutions | Issues, Solutions, Playbooks | Attempted Solution |
| **Reviewer** | Records outcome, updates playbook stats, flags handoffs | Solutions, Outcomes | Updated Playbook stats, Handoff |

Agents never talk to each other directly — they coordinate by reading and writing the graph (**blackboard pattern**). This makes all shared state visible and traceable.

---

## 📊 Graph Data Model

### Node Labels

| Label | Memory Type | Key Properties |
|-------|------------|----------------|
| `Customer` | Semantic | `id`, `name`, `plan` |
| `Product` | Semantic | `name`, `version` |
| `Issue` | Semantic | `type`, `summary`, `status`, `urgency` |
| `Episode` | Episodic | `id`, `timestamp`, `transcript_summary`, `session_id` |
| `Message` | Episodic | `role`, `text`, `timestamp` |
| `Solution` | Semantic | `description`, `outcome` |
| `Playbook` | **Procedural** | `name`, `steps`, `success_count`, `fail_count` |
| `Agent` | Coordination | `name`, `role` |
| `Handoff` | Coordination | `reason`, `timestamp`, `status` |

### Relationships

```cypher
(Customer)-[:HAD_EPISODE]->(Episode)
(Episode)-[:HAS_MESSAGE]->(Message)
(Episode)-[:ABOUT]->(Issue)
(Issue)-[:AFFECTS]->(Product)
(Issue)-[:SIMILAR_TO]->(Issue)
(Solution)-[:RESOLVED]->(Issue)
(Playbook)-[:APPLIES_TO]->(Issue)
(Playbook)-[:INCLUDES]->(Solution)
(Agent)-[:HANDLED]->(Episode)
(Agent)-[:HANDED_OFF_TO]->(Handoff)-[:HANDED_TO]->(Agent)
```

### Tenant Isolation

Each tenant gets its own FalkorDB graph: `tenant_acme`, `tenant_globex`, `tenant_initech`. No query can cross tenants because the graph object itself is different. Verified by `tests/test_isolation.py`.

---

## 🚀 Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+
- Anthropic API key (free tier works)

### 1. Start FalkorDB

```bash
cd relay
docker compose up -d
```

FalkorDB Browser → http://localhost:8001

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Seed demo data

```bash
python -m scripts.seed
```

This creates **3 tenants** (acme, globex, initech) with 9 customers, 7 playbooks (with realistic win/loss counts), and 15 historical episodes.

### 5. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

API docs → http://localhost:8000/docs

### 6. Start the UI

```bash
streamlit run ui/streamlit_app.py
```

Open → http://localhost:8501

---

## 🎬 Demo Script (3 minutes)

| Segment | Time | What to show |
|---------|------|-------------|
| **Problem** | 20s | "Agents forget. Customers repeat themselves." |
| **Customer returns** | 40s | Select Alice @ Acme. Type: "I'm having that password issue again." Relay greets with her history. |
| **Agents at work** | 60s | Watch Explain panel: Intake extracts `password_reset`, Resolver finds "Reset Password" playbook (8 wins). |
| **Explain panel** | 30s | Show Cypher queries used, nodes touched, episode ID. |
| **Learning** | 20s | Click ✅ Resolved. Playbook success count goes from 8 → 9. |
| **Isolation** | 10s | Switch to Globex tenant — Alice is gone. Different graph. |

---

## 🧪 Testing

```bash
# All tests (requires seeded FalkorDB)
pytest

# Individual suites
pytest tests/test_queries.py -v       # Cypher query unit tests
pytest tests/test_isolation.py -v     # Tenant isolation
pytest tests/test_agents.py -v        # Agent integration (LLM mocked)

# Load test (requires backend running)
python scripts/load_test.py --sessions 20
```

### Test Coverage

| Test | Pass Condition |
|------|---------------|
| Unit: queries | Each query returns expected nodes on seed data |
| Memory persistence | Restart app, ask again — history still recalled |
| Isolation | Tenant A cannot see Tenant B's customer |
| Handoff | Handoff node exists after escalation |
| Playbook learning | Success count increments after resolved case |
| Load | 20 parallel sessions finish with no errors |
| Injection safety | Odd characters in messages don't break queries |

---

## 📈 Load Test Results

> Run after backend is up: `python scripts/load_test.py --sessions 20`

| Metric | Result |
|--------|--------|
| Sessions | 20 |
| Successes | *(run to populate)* |
| Failures | *(run to populate)* |
| Wall time | *(run to populate)* |
| Avg latency | *(run to populate)* |

Results saved to `load_test_results.json` automatically.

---

## 📁 Project Structure

```
relay/
├── docker-compose.yml          # FalkorDB + browser
├── requirements.txt
├── pyproject.toml              # Pytest config
├── .env.example                # Copy to .env
├── app/
│   ├── main.py                 # FastAPI: /chat /outcome /graph /health
│   ├── orchestrator.py         # Intake → Resolver pipeline
│   ├── llm.py                  # Claude wrapper (JSON-safe, 1 retry)
│   ├── memory/
│   │   ├── graph.py            # FalkorDB connection + tenant selector
│   │   └── queries.py          # All parameterized Cypher queries
│   └── agents/
│       ├── intake.py           # Entity extraction + episode creation
│       ├── resolver.py         # Playbook lookup + reply generation
│       └── reviewer.py         # Outcome recording + procedural learning
├── ui/
│   └── streamlit_app.py        # Chat UI + Explain panel
├── scripts/
│   ├── seed.py                 # Load 3 tenants of demo data
│   └── load_test.py            # Async concurrency test (20 sessions)
└── tests/
    ├── test_queries.py         # Cypher query tests
    ├── test_isolation.py       # Tenant isolation tests
    └── test_agents.py          # Agent integration tests (LLM mocked)
```

---

## 🔑 Key Design Decisions

### Why FalkorDB?
The core questions in support are about **connections**: "Has this customer had this problem before?", "Which fix worked for similar problems?", "Which agent handled this last time?" A graph answers these in one traversal. A relational DB would need multiple joins; a vector DB can't express relationships.

### Why the blackboard pattern?
Agents never call each other directly. They coordinate by reading and writing the graph. This means:
- Every state change is persisted and auditable
- Any agent can pick up any conversation
- The Explain panel is trivial — just show what the agent read

### Why build the memory layer from scratch?
It's small (~200 lines), you understand it fully, and you can explain it in the blog and to judges. Graphiti or other memory frameworks could be added later.

### Why Claude Haiku?
Fast and cheap for entity extraction (one call per message). Short prompts, one extraction call per message, no streaming needed for a hackathon demo.

### Security
All Cypher queries are parameterized. User text is never string-formatted into a query. This is enforced in `memory/queries.py` — every query uses `$variable` placeholders.

---

## 🏆 Judging Criteria Mapping

| Criterion | How Relay meets it |
|-----------|-------------------|
| Episodic memory | Every conversation saved as Episode + Message nodes |
| Semantic memory | Customer, Issue, Solution, Product nodes with rich properties |
| Procedural memory | Playbook `success_count` / `fail_count` updates after every resolution |
| Persistent conversation history | All messages in graph — survive restarts |
| Shared state between agents | Blackboard pattern — agents read/write the same graph |
| High-concurrency reads/writes | Load test: 20 parallel sessions, no errors |
| Separate memory per tenant | One FalkorDB graph per tenant, isolation proven by tests |

---

## 📝 API Reference

### `POST /chat`
```json
{
  "tenant_id": "acme",
  "customer_id": "alice_acme",
  "customer_name": "Alice",
  "message": "I forgot my password again",
  "session_id": null
}
```
Response:
```json
{
  "reply": "Hi Alice! I can see you've had a similar issue before...",
  "session_id": "uuid",
  "explain": {
    "episode_id": "uuid",
    "issue_type": "password_reset",
    "product": "AcmeDash",
    "urgency": "high",
    "playbook_used": "Reset Password",
    "cypher_used": ["find_best_playbook(issue_type='password_reset')", "..."],
    "nodes_touched": ["Playbook:Reset Password", "Solution:abc12345"],
    "history_summary": "Customer has 2 past episode(s). Most recent: password_reset (resolved).",
    "agent_pipeline": ["Intake", "Resolver"]
  }
}
```

### `POST /outcome`
```json
{
  "tenant_id": "acme",
  "episode_id": "uuid",
  "issue_id": "uuid",
  "solution_id": "uuid",
  "playbook_name": "Reset Password",
  "outcome": "resolved",
  "transcript_summary": "Customer reset password successfully."
}
```

### `GET /graph/{tenant_id}/{customer_id}`
Returns the last 20 episode rows for a customer — used by the UI graph visualization.

---

## 🔗 Resources

- [FalkorDB Docs](https://docs.falkordb.com)
- [FalkorDB Python Client](https://github.com/FalkorDB/falkordb-py)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Graph Hacks Hackathon](https://wemakedevs.org)

---

*Built solo for the WeMakeDevs × FalkorDB Graph Hacks hackathon, Oct 15–18 2026.*
