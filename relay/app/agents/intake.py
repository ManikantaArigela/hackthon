"""
agents/intake.py
Intake Agent — understands the customer's message, extracts entities,
recalls history, and opens a new Episode in the graph.

Input:  tenant_id, customer_id, user_message, session_id
Output: IntakeResult dict
"""

from dataclasses import dataclass, field

from app.llm import llm_call_json
from app.memory.graph import get_graph
from app.memory.queries import (
    ensure_customer,
    recall_customer_episodes,
    create_episode,
    append_message,
    link_issue_to_episode,
)


@dataclass
class IntakeResult:
    episode_id: str
    issue_id: str
    issue_type: str
    product: str
    urgency: str
    customer_history: list[dict] = field(default_factory=list)
    history_summary: str = ""


SYSTEM_PROMPT = """You are an AI support intake agent.
Given a customer message and their recent support history, extract:
- issue_type: short category (e.g. 'password_reset', 'billing', 'login_error', 'feature_request')
- product: product name mentioned, or 'unknown'
- urgency: 'low' | 'medium' | 'high'
- issue_summary: one sentence describing the issue

Respond with JSON only."""


def run(tenant_id: str, customer_id: str, customer_name: str,
        user_message: str, session_id: str) -> IntakeResult:
    """
    1. Ensure customer node exists in the tenant graph
    2. Recall last 5 episodes for context
    3. LLM extracts {issue_type, product, urgency, issue_summary}
    4. Create Episode + Message + Issue nodes
    5. Return IntakeResult
    """
    graph = get_graph(tenant_id)
    ensure_customer(graph, customer_id, name=customer_name)

    # --- Step 1: recall history ---
    history = recall_customer_episodes(graph, customer_id, limit=5)
    history_text = ""
    if history:
        lines = [
            f"- [{h['timestamp'][:10]}] {h['issue_type']}: {h['issue_summary']} (status: {h['status']})"
            for h in history
        ]
        history_text = "Recent history:\n" + "\n".join(lines)

    # --- Step 2: LLM extraction ---
    user_prompt = f"Customer message: {user_message}\n\n{history_text}"
    extracted = llm_call_json(SYSTEM_PROMPT, user_prompt)

    issue_type = extracted.get("issue_type", "general")
    product = extracted.get("product", "unknown")
    urgency = extracted.get("urgency", "medium")
    issue_summary = extracted.get("issue_summary", user_message[:120])

    # Build human-readable history summary for the resolver
    if history:
        history_summary = f"Customer has {len(history)} past episode(s). Most recent: {history[0]['issue_type']} ({history[0]['status']})."
    else:
        history_summary = "New customer — no prior episodes."

    # --- Step 3: write to graph ---
    episode_id = create_episode(graph, customer_id, session_id)
    append_message(graph, episode_id, role="user", text=user_message)
    issue_id = link_issue_to_episode(
        graph, episode_id, issue_type, issue_summary, product, urgency
    )

    return IntakeResult(
        episode_id=episode_id,
        issue_id=issue_id,
        issue_type=issue_type,
        product=product,
        urgency=urgency,
        customer_history=history,
        history_summary=history_summary,
    )
