"""
agents/resolver.py
Resolver Agent — finds the best playbook and past solutions from the graph,
generates a reply, and records the attempted solution.

Input:  tenant_id, issue_type, episode_id, issue_id, history_summary
Output: ResolverResult dict
"""

from dataclasses import dataclass, field

from app.llm import llm_call
from app.memory.graph import get_graph
from app.memory.queries import (
    find_best_playbook,
    find_similar_solutions,
    append_message,
    record_solution,
)


@dataclass
class ResolverResult:
    reply: str
    solution_id: str
    playbook_used: str | None
    cypher_used: list[str]
    nodes_touched: list[str]


SYSTEM_PROMPT = """You are a helpful AI customer support resolver.
Given a customer's issue and the best available playbook steps and past solutions,
write a clear, empathetic support reply that:
1. Acknowledges the issue
2. Provides step-by-step help based on the playbook
3. Mentions if this worked for similar customers before

Keep the reply under 150 words. Be friendly and direct."""


def run(tenant_id: str, issue_type: str, episode_id: str, issue_id: str,
        history_summary: str) -> ResolverResult:
    """
    1. Query graph for best playbooks and similar solutions
    2. LLM generates reply using that context
    3. Save attempted solution node
    4. Return ResolverResult with explain metadata
    """
    graph = get_graph(tenant_id)

    # --- Step 1: graph reads ---
    playbooks = find_best_playbook(graph, issue_type, limit=3)
    solutions = find_similar_solutions(graph, issue_type, limit=3)

    cypher_used = [
        f"find_best_playbook(issue_type='{issue_type}')",
        f"find_similar_solutions(issue_type='{issue_type}')",
    ]
    nodes_touched = []

    # Build context for LLM
    playbook_text = ""
    playbook_name = None
    if playbooks:
        best = playbooks[0]
        playbook_name = best["name"]
        nodes_touched.append(f"Playbook:{playbook_name}")
        steps = best.get("steps") or "No specific steps recorded."
        wins = best.get("success_count", 0)
        playbook_text = (
            f"Best playbook: '{playbook_name}' ({wins} successful resolutions)\n"
            f"Steps: {steps}"
        )

    solution_text = ""
    if solutions:
        sol_lines = [f"- {s['description']} (used {s['times']} times)" for s in solutions]
        solution_text = "Past solutions that worked:\n" + "\n".join(sol_lines)
        nodes_touched += [f"Solution:{s['description'][:30]}" for s in solutions]

    user_prompt = (
        f"Issue type: {issue_type}\n"
        f"Customer context: {history_summary}\n\n"
        f"{playbook_text}\n\n"
        f"{solution_text}"
    )

    # --- Step 2: LLM reply ---
    reply = llm_call(SYSTEM_PROMPT, user_prompt)

    # --- Step 3: record attempted solution ---
    solution_desc = f"Used playbook '{playbook_name}' for {issue_type}" if playbook_name else f"No playbook found for {issue_type}"
    solution_id = record_solution(graph, issue_id, solution_desc, outcome="attempted")
    append_message(graph, episode_id, role="assistant", text=reply)
    nodes_touched.append(f"Solution:{solution_id[:8]}")

    return ResolverResult(
        reply=reply,
        solution_id=solution_id,
        playbook_used=playbook_name,
        cypher_used=cypher_used,
        nodes_touched=nodes_touched,
    )
