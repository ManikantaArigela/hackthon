"""
orchestrator.py
Runs the Intake → Resolver pipeline for a single chat turn.
Reviewer is triggered separately via /outcome endpoint.
"""

import uuid

from app.agents import intake, resolver
from app.agents.intake import IntakeResult
from app.agents.resolver import ResolverResult


def chat(
    tenant_id: str,
    customer_id: str,
    customer_name: str,
    user_message: str,
    session_id: str | None = None,
) -> dict:
    """
    Full pipeline for one chat turn.
    Returns everything the UI needs: reply + explain metadata.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    # --- Intake ---
    intake_result: IntakeResult = intake.run(
        tenant_id=tenant_id,
        customer_id=customer_id,
        customer_name=customer_name,
        user_message=user_message,
        session_id=session_id,
    )

    # --- Resolver ---
    resolver_result: ResolverResult = resolver.run(
        tenant_id=tenant_id,
        issue_type=intake_result.issue_type,
        episode_id=intake_result.episode_id,
        issue_id=intake_result.issue_id,
        history_summary=intake_result.history_summary,
    )

    return {
        "reply": resolver_result.reply,
        "session_id": session_id,
        "explain": {
            "episode_id": intake_result.episode_id,
            "issue_id": intake_result.issue_id,
            "solution_id": resolver_result.solution_id,
            "issue_type": intake_result.issue_type,
            "product": intake_result.product,
            "urgency": intake_result.urgency,
            "playbook_used": resolver_result.playbook_used,
            "cypher_used": resolver_result.cypher_used,
            "nodes_touched": resolver_result.nodes_touched,
            "customer_history_count": len(intake_result.customer_history),
            "history_summary": intake_result.history_summary,
            "agent_pipeline": ["Intake", "Resolver"],
        },
    }
