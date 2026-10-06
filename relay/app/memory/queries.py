"""
memory/queries.py
All Cypher queries for the Relay memory layer.
IMPORTANT: Every query uses parameterized inputs — never string-format user text into Cypher.
"""

import uuid
from datetime import datetime, timezone

import falkordb


# ─────────────────────────────────────────────
# READ QUERIES
# ─────────────────────────────────────────────

def recall_customer_episodes(graph: falkordb.Graph, customer_id: str, limit: int = 5) -> list[dict]:
    """
    Return the last N episodes for a customer, each with its issue summary.
    Memory type: Episodic
    """
    query = """
    MATCH (c:Customer {id: $cid})-[:HAD_EPISODE]->(e:Episode)-[:ABOUT]->(i:Issue)
    RETURN e.id AS episode_id,
           e.timestamp AS timestamp,
           e.transcript_summary AS summary,
           i.type AS issue_type,
           i.summary AS issue_summary,
           i.status AS status
    ORDER BY e.timestamp DESC
    LIMIT $limit
    """
    result = graph.query(query, {"cid": customer_id, "limit": limit})
    return [dict(zip([h for h in result.header], row)) for row in result.result_set]


def find_best_playbook(graph: falkordb.Graph, issue_type: str, limit: int = 3) -> list[dict]:
    """
    Return the top N playbooks for a given issue type, ranked by success count.
    Memory type: Procedural
    """
    query = """
    MATCH (p:Playbook)-[:APPLIES_TO]->(i:Issue {type: $issue_type})
    RETURN p.name AS name,
           p.steps AS steps,
           p.success_count AS success_count,
           p.fail_count AS fail_count
    ORDER BY p.success_count DESC
    LIMIT $limit
    """
    result = graph.query(query, {"issue_type": issue_type, "limit": limit})
    return [dict(zip([h for h in result.header], row)) for row in result.result_set]


def find_similar_solutions(graph: falkordb.Graph, issue_type: str, limit: int = 3) -> list[dict]:
    """
    Return solutions that resolved similar issues.
    Memory type: Semantic
    """
    query = """
    MATCH (i:Issue {type: $issue_type})<-[:SIMILAR_TO*0..2]-(j:Issue)<-[:RESOLVED]-(s:Solution)
    RETURN s.description AS description, count(*) AS times
    ORDER BY times DESC
    LIMIT $limit
    """
    result = graph.query(query, {"issue_type": issue_type, "limit": limit})
    return [dict(zip([h for h in result.header], row)) for row in result.result_set]


# ─────────────────────────────────────────────
# WRITE QUERIES
# ─────────────────────────────────────────────

def ensure_customer(graph: falkordb.Graph, customer_id: str, name: str = "", plan: str = "free") -> None:
    """Upsert a Customer node."""
    query = """
    MERGE (c:Customer {id: $cid})
    ON CREATE SET c.name = $name, c.plan = $plan
    """
    graph.query(query, {"cid": customer_id, "name": name, "plan": plan})


def create_episode(graph: falkordb.Graph, customer_id: str, session_id: str) -> str:
    """
    Create a new Episode node linked to the customer.
    Returns the new episode_id.
    Memory type: Episodic
    """
    episode_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    query = """
    MATCH (c:Customer {id: $cid})
    CREATE (e:Episode {
        id: $eid,
        session_id: $sid,
        timestamp: $ts,
        transcript_summary: ''
    })
    CREATE (c)-[:HAD_EPISODE]->(e)
    """
    graph.query(query, {
        "cid": customer_id,
        "eid": episode_id,
        "sid": session_id,
        "ts": ts,
    })
    return episode_id


def append_message(graph: falkordb.Graph, episode_id: str, role: str, text: str) -> None:
    """
    Append a Message node to an Episode.
    role: 'user' | 'assistant'
    """
    msg_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    query = """
    MATCH (e:Episode {id: $eid})
    CREATE (m:Message {id: $mid, role: $role, text: $text, timestamp: $ts})
    CREATE (e)-[:HAS_MESSAGE]->(m)
    """
    graph.query(query, {"eid": episode_id, "mid": msg_id, "role": role, "text": text, "ts": ts})


def link_issue_to_episode(graph: falkordb.Graph, episode_id: str, issue_type: str,
                           issue_summary: str, product: str, urgency: str) -> str:
    """
    Create an Issue node and link it to the episode.
    Returns the issue node id.
    """
    issue_id = str(uuid.uuid4())
    query = """
    MATCH (e:Episode {id: $eid})
    CREATE (i:Issue {
        id: $iid,
        type: $type,
        summary: $summary,
        product: $product,
        urgency: $urgency,
        status: 'open'
    })
    CREATE (e)-[:ABOUT]->(i)
    """
    graph.query(query, {
        "eid": episode_id,
        "iid": issue_id,
        "type": issue_type,
        "summary": issue_summary,
        "product": product,
        "urgency": urgency,
    })
    return issue_id


def record_solution(graph: falkordb.Graph, issue_id: str, solution_desc: str,
                    outcome: str = "attempted") -> str:
    """
    Create a Solution node and link it to the issue.
    outcome: 'attempted' | 'resolved' | 'escalated'
    Returns solution_id.
    """
    sol_id = str(uuid.uuid4())
    query = """
    MATCH (i:Issue {id: $iid})
    CREATE (s:Solution {id: $sid, description: $desc, outcome: $outcome})
    CREATE (s)-[:RESOLVED]->(i)
    SET i.status = $outcome
    """
    graph.query(query, {"iid": issue_id, "sid": sol_id, "desc": solution_desc, "outcome": outcome})
    return sol_id


def update_playbook_count(graph: falkordb.Graph, playbook_name: str, success: bool) -> None:
    """
    Increment the success_count or fail_count of a Playbook node.
    This is how procedural memory improves over time.
    """
    if success:
        query = """
        MATCH (p:Playbook {name: $name})
        SET p.success_count = p.success_count + 1
        """
    else:
        query = """
        MATCH (p:Playbook {name: $name})
        SET p.fail_count = p.fail_count + 1
        """
    graph.query(query, {"name": playbook_name})


def record_handoff(graph: falkordb.Graph, from_agent: str, to_agent: str,
                   reason: str, episode_id: str) -> str:
    """
    Create a Handoff node and link the two Agent nodes through it.
    Returns the handoff node id.
    """
    handoff_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    query = """
    MERGE (a1:Agent {name: $from_agent})
    MERGE (a2:Agent {name: $to_agent})
    CREATE (h:Handoff {
        id: $hid,
        reason: $reason,
        timestamp: $ts,
        status: 'pending',
        episode_id: $eid
    })
    CREATE (a1)-[:HANDED_OFF_TO]->(h)
    CREATE (h)-[:HANDED_TO]->(a2)
    """
    graph.query(query, {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "hid": handoff_id,
        "reason": reason,
        "ts": ts,
        "eid": episode_id,
    })
    return handoff_id


def update_episode_summary(graph: falkordb.Graph, episode_id: str, summary: str) -> None:
    """Update the transcript_summary of an episode after it closes."""
    query = """
    MATCH (e:Episode {id: $eid})
    SET e.transcript_summary = $summary
    """
    graph.query(query, {"eid": episode_id, "summary": summary})
