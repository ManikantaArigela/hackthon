"""
agents/reviewer.py
Reviewer Agent — records the outcome after a user signals resolution or escalation.
Updates playbook success/fail counts (procedural memory).
Creates Handoff node if escalated.

Input:  tenant_id, episode_id, issue_id, solution_id, playbook_name, outcome
Output: ReviewerResult dict
"""

from dataclasses import dataclass

from app.memory.graph import get_graph
from app.memory.queries import (
    update_playbook_count,
    record_solution,
    record_handoff,
    update_episode_summary,
)


@dataclass
class ReviewerResult:
    outcome: str
    playbook_updated: str | None
    handoff_id: str | None
    summary_written: bool


def run(
    tenant_id: str,
    episode_id: str,
    issue_id: str,
    solution_id: str,
    playbook_name: str | None,
    outcome: str,             # 'resolved' | 'escalated' | 'pending'
    transcript_summary: str = "",
) -> ReviewerResult:
    """
    1. If outcome is resolved/escalated, update the solution node status
    2. Update playbook success or fail count
    3. If escalated, create a Handoff node
    4. Write episode transcript summary
    """
    graph = get_graph(tenant_id)
    handoff_id = None

    # --- Step 1: update solution outcome ---
    if outcome in ("resolved", "escalated"):
        # Re-record with final outcome (overwrites 'attempted')
        record_solution(graph, issue_id, f"Outcome: {outcome}", outcome=outcome)

    # --- Step 2: update playbook counts ---
    if playbook_name and outcome in ("resolved", "escalated"):
        success = outcome == "resolved"
        update_playbook_count(graph, playbook_name, success=success)

    # --- Step 3: handoff if escalated ---
    if outcome == "escalated":
        handoff_id = record_handoff(
            graph,
            from_agent="Resolver",
            to_agent="Intake",
            reason="Customer issue not resolved — escalating for human review",
            episode_id=episode_id,
        )

    # --- Step 4: write summary ---
    summary_written = False
    if transcript_summary:
        update_episode_summary(graph, episode_id, transcript_summary)
        summary_written = True

    return ReviewerResult(
        outcome=outcome,
        playbook_updated=playbook_name if playbook_name and outcome in ("resolved", "escalated") else None,
        handoff_id=handoff_id,
        summary_written=summary_written,
    )
