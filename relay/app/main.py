"""
main.py
FastAPI entry point for the Relay backend.

Endpoints:
  POST /chat      — send a message, get reply + explain
  POST /outcome   — record resolved/escalated outcome (triggers Reviewer)
  GET  /graph/{tenant_id}/{customer_id} — node list for visualization
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import orchestrator
from app.agents import reviewer
from app.memory.graph import get_graph

app = FastAPI(title="Relay — Graph-Memory Agent", version="0.1.0")


# ─── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    tenant_id: str
    customer_id: str
    customer_name: str = "Customer"
    message: str
    session_id: str | None = None


class OutcomeRequest(BaseModel):
    tenant_id: str
    episode_id: str
    issue_id: str
    solution_id: str
    playbook_name: str | None = None
    outcome: str          # 'resolved' | 'escalated' | 'pending'
    transcript_summary: str = ""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    """Main chat endpoint. Runs Intake → Resolver pipeline."""
    try:
        result = orchestrator.chat(
            tenant_id=req.tenant_id,
            customer_id=req.customer_id,
            customer_name=req.customer_name,
            user_message=req.message,
            session_id=req.session_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/outcome")
def record_outcome(req: OutcomeRequest) -> dict:
    """Trigger Reviewer agent after user signals resolution or escalation."""
    if req.outcome not in ("resolved", "escalated", "pending"):
        raise HTTPException(status_code=400, detail="outcome must be resolved|escalated|pending")
    try:
        result = reviewer.run(
            tenant_id=req.tenant_id,
            episode_id=req.episode_id,
            issue_id=req.issue_id,
            solution_id=req.solution_id,
            playbook_name=req.playbook_name,
            outcome=req.outcome,
            transcript_summary=req.transcript_summary,
        )
        return {
            "outcome": result.outcome,
            "playbook_updated": result.playbook_updated,
            "handoff_id": result.handoff_id,
            "summary_written": result.summary_written,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/{tenant_id}/{customer_id}")
def get_customer_graph(tenant_id: str, customer_id: str) -> dict:
    """Return nodes and edges for a customer's episode graph (for visualization)."""
    try:
        graph = get_graph(tenant_id)
        query = """
        MATCH (c:Customer {id: $cid})-[:HAD_EPISODE]->(e:Episode)
        OPTIONAL MATCH (e)-[:ABOUT]->(i:Issue)
        OPTIONAL MATCH (s:Solution)-[:RESOLVED]->(i)
        RETURN c.id AS customer, e.id AS episode, e.timestamp AS ts,
               i.type AS issue_type, i.status AS status,
               s.description AS solution
        ORDER BY e.timestamp DESC
        LIMIT 20
        """
        result = graph.query(query, {"cid": customer_id})
        rows = [dict(zip([h for h in result.header], row)) for row in result.result_set]
        return {"tenant_id": tenant_id, "customer_id": customer_id, "nodes": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
