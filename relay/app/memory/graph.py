"""
memory/graph.py
FalkorDB connection and tenant-scoped graph selector.
"""

import os
import falkordb
from dotenv import load_dotenv

load_dotenv()

_client: falkordb.FalkorDB | None = None


def get_client() -> falkordb.FalkorDB:
    """Return a singleton FalkorDB client."""
    global _client
    if _client is None:
        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", 6379))
        _client = falkordb.FalkorDB(host=host, port=port)
    return _client


def get_graph(tenant_id: str) -> falkordb.Graph:
    """
    Return the graph for a given tenant.
    Each tenant gets its own isolated graph: 'tenant_<tenant_id>'.
    """
    return get_client().select_graph(f"tenant_{tenant_id}")


def ensure_indexes(tenant_id: str) -> None:
    """
    Create indexes on Customer.id and Issue.type for fast lookups.
    Safe to call multiple times — FalkorDB ignores duplicate index creation.
    """
    g = get_graph(tenant_id)
    try:
        g.query("CREATE INDEX FOR (c:Customer) ON (c.id)")
    except Exception:
        pass  # Index already exists
    try:
        g.query("CREATE INDEX FOR (i:Issue) ON (i.type)")
    except Exception:
        pass
