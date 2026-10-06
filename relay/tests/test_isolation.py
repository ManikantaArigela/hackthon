"""
tests/test_isolation.py
Verifies that tenant A cannot read tenant B's data.
This is a key judging criterion (FR8).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.memory.graph import get_graph
from app.memory.queries import ensure_customer, recall_customer_episodes


def test_tenant_isolation():
    """
    A customer in 'acme' graph must NOT appear in 'globex' graph.
    alice_acme is seeded in acme only.
    """
    # alice_acme exists in acme
    acme_graph = get_graph("acme")
    acme_result = acme_graph.query(
        "MATCH (c:Customer {id: $cid}) RETURN c.id",
        {"cid": "alice_acme"}
    )
    assert len(acme_result.result_set) == 1, "alice_acme should exist in acme"

    # alice_acme must NOT exist in globex
    globex_graph = get_graph("globex")
    globex_result = globex_graph.query(
        "MATCH (c:Customer {id: $cid}) RETURN c.id",
        {"cid": "alice_acme"}
    )
    assert len(globex_result.result_set) == 0, "alice_acme must NOT appear in globex graph"


def test_episodes_do_not_cross_tenants():
    """Episodes created in acme should not appear in globex."""
    acme_episodes = recall_customer_episodes(get_graph("acme"), "alice_acme")
    globex_episodes = recall_customer_episodes(get_graph("globex"), "alice_acme")

    assert len(acme_episodes) > 0, "acme alice should have episodes"
    assert len(globex_episodes) == 0, "globex should have no episodes for alice_acme"
