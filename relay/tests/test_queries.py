"""
tests/test_queries.py
Unit tests for the memory/queries.py module.
Run AFTER seeding: python -m scripts.seed
Then: pytest tests/test_queries.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.memory.graph import get_graph, ensure_indexes
from app.memory.queries import (
    ensure_customer,
    recall_customer_episodes,
    find_best_playbook,
    create_episode,
    append_message,
    link_issue_to_episode,
    record_solution,
    update_playbook_count,
    record_handoff,
)

TENANT = "acme"  # seeded tenant

@pytest.fixture(scope="module")
def graph():
    return get_graph(TENANT)


def test_recall_customer_episodes_returns_history(graph):
    """Alice should have past episodes after seeding."""
    episodes = recall_customer_episodes(graph, "alice_acme", limit=5)
    assert len(episodes) > 0, "Alice should have seeded episodes"
    assert "issue_type" in episodes[0]
    assert "timestamp" in episodes[0]


def test_find_best_playbook_returns_ranked_results(graph):
    """Password Reset playbook should be top result for password_reset issue type."""
    playbooks = find_best_playbook(graph, "password_reset", limit=3)
    assert len(playbooks) > 0, "Should find at least one playbook for password_reset"
    assert playbooks[0]["name"] == "Reset Password"
    assert playbooks[0]["success_count"] >= 8


def test_create_episode_and_append_messages(graph):
    """Create a new episode and add messages — both should appear in graph."""
    ensure_customer(graph, "test_user_001", name="Tester", plan="free")
    ep_id = create_episode(graph, "test_user_001", session_id="sess_test_001")
    assert ep_id is not None

    append_message(graph, ep_id, role="user", text="My test message")
    append_message(graph, ep_id, role="assistant", text="Here is the reply")

    # Verify messages exist
    result = graph.query(
        "MATCH (e:Episode {id: $eid})-[:HAS_MESSAGE]->(m:Message) RETURN m.role, m.text",
        {"eid": ep_id}
    )
    rows = result.result_set
    assert len(rows) == 2
    roles = {r[0] for r in rows}
    assert "user" in roles
    assert "assistant" in roles


def test_link_issue_and_record_solution(graph):
    """Create issue + solution and verify they're linked."""
    ensure_customer(graph, "test_user_002", name="IssueUser", plan="pro")
    ep_id = create_episode(graph, "test_user_002", session_id="sess_test_002")
    issue_id = link_issue_to_episode(graph, ep_id, "billing", "Overcharged", "AcmeDash", "high")
    assert issue_id is not None

    sol_id = record_solution(graph, issue_id, "Issued refund for overcharge", outcome="resolved")
    assert sol_id is not None

    result = graph.query(
        "MATCH (s:Solution {id: $sid})-[:RESOLVED]->(i:Issue {id: $iid}) RETURN i.status",
        {"sid": sol_id, "iid": issue_id}
    )
    assert len(result.result_set) == 1
    assert result.result_set[0][0] == "resolved"


def test_update_playbook_count_increments(graph):
    """Updating a playbook count should increment the right field."""
    # Get current count
    before = graph.query(
        "MATCH (p:Playbook {name: 'Reset Password'}) RETURN p.success_count"
    ).result_set[0][0]

    update_playbook_count(graph, "Reset Password", success=True)

    after = graph.query(
        "MATCH (p:Playbook {name: 'Reset Password'}) RETURN p.success_count"
    ).result_set[0][0]

    assert after == before + 1


def test_record_handoff_creates_node(graph):
    """Handoff node should be created between two Agent nodes."""
    ensure_customer(graph, "test_user_003", name="HandoffUser", plan="free")
    ep_id = create_episode(graph, "test_user_003", session_id="sess_test_003")
    handoff_id = record_handoff(graph, "Resolver", "Intake", "Escalated by user", ep_id)
    assert handoff_id is not None

    result = graph.query(
        "MATCH (a1:Agent {name: 'Resolver'})-[:HANDED_OFF_TO]->(h:Handoff {id: $hid}) RETURN h.reason",
        {"hid": handoff_id}
    )
    assert len(result.result_set) == 1
    assert "Escalated" in result.result_set[0][0]
