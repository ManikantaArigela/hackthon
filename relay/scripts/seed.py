"""
scripts/seed.py
Load demo data into FalkorDB for 3 tenants.
Run: python -m scripts.seed  (from relay/ root)

Creates:
  - 3 tenants: acme, globex, initech
  - 3 customers per tenant
  - 2 products per tenant
  - 2-3 playbooks with steps + success/fail counts
  - 5 historical episodes per customer with messages, issues, solutions
"""

import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.memory.graph import get_graph, ensure_indexes
from app.memory.queries import (
    ensure_customer,
    create_episode,
    append_message,
    link_issue_to_episode,
    record_solution,
    update_playbook_count,
)

# ─── Demo data ────────────────────────────────────────────────────────────────

TENANTS = {
    "acme": {
        "customers": [
            {"id": "alice_acme", "name": "Alice", "plan": "enterprise"},
            {"id": "bob_acme",   "name": "Bob",   "plan": "pro"},
            {"id": "carol_acme", "name": "Carol", "plan": "free"},
        ],
        "playbooks": [
            {
                "name": "Reset Password",
                "issue_type": "password_reset",
                "steps": "1. Go to /forgot-password 2. Enter email 3. Check inbox 4. Click reset link",
                "success_count": 8,
                "fail_count": 1,
            },
            {
                "name": "Fix Login Error",
                "issue_type": "login_error",
                "steps": "1. Clear browser cache 2. Try incognito 3. Check caps lock 4. Reset password if needed",
                "success_count": 5,
                "fail_count": 2,
            },
            {
                "name": "Billing Dispute",
                "issue_type": "billing",
                "steps": "1. Verify invoice ID 2. Check plan dates 3. Issue refund if valid 4. Send confirmation",
                "success_count": 3,
                "fail_count": 0,
            },
        ],
        "episodes": [
            {"customer": "alice_acme", "issue_type": "password_reset", "product": "AcmeDash",  "urgency": "high",   "status": "resolved"},
            {"customer": "alice_acme", "issue_type": "billing",        "product": "AcmeDash",  "urgency": "medium", "status": "resolved"},
            {"customer": "bob_acme",   "issue_type": "login_error",    "product": "AcmeAPI",   "urgency": "high",   "status": "resolved"},
            {"customer": "bob_acme",   "issue_type": "password_reset", "product": "AcmeDash",  "urgency": "low",    "status": "resolved"},
            {"customer": "carol_acme", "issue_type": "billing",        "product": "AcmeDash",  "urgency": "medium", "status": "escalated"},
        ],
    },
    "globex": {
        "customers": [
            {"id": "dan_globex",  "name": "Dan",   "plan": "enterprise"},
            {"id": "eve_globex",  "name": "Eve",   "plan": "pro"},
            {"id": "frank_globex","name": "Frank", "plan": "free"},
        ],
        "playbooks": [
            {
                "name": "API Key Rotation",
                "issue_type": "api_key",
                "steps": "1. Log into dashboard 2. Go to API settings 3. Generate new key 4. Update env vars",
                "success_count": 6,
                "fail_count": 0,
            },
            {
                "name": "Slow Query Fix",
                "issue_type": "performance",
                "steps": "1. Enable query logging 2. Identify slow query 3. Add index 4. Test with EXPLAIN",
                "success_count": 4,
                "fail_count": 1,
            },
        ],
        "episodes": [
            {"customer": "dan_globex",  "issue_type": "api_key",     "product": "GlobexAPI",  "urgency": "high",   "status": "resolved"},
            {"customer": "dan_globex",  "issue_type": "performance",  "product": "GlobexDB",   "urgency": "medium", "status": "resolved"},
            {"customer": "eve_globex",  "issue_type": "api_key",     "product": "GlobexAPI",  "urgency": "low",    "status": "resolved"},
            {"customer": "frank_globex","issue_type": "performance",  "product": "GlobexDB",   "urgency": "high",   "status": "escalated"},
            {"customer": "frank_globex","issue_type": "api_key",     "product": "GlobexAPI",  "urgency": "medium", "status": "resolved"},
        ],
    },
    "initech": {
        "customers": [
            {"id": "grace_initech", "name": "Grace", "plan": "enterprise"},
            {"id": "henry_initech", "name": "Henry", "plan": "pro"},
            {"id": "ivan_initech",  "name": "Ivan",  "plan": "free"},
        ],
        "playbooks": [
            {
                "name": "TPS Report Fix",
                "issue_type": "report_error",
                "steps": "1. Check report template version 2. Re-run with --verbose 3. Clear report cache 4. Regenerate",
                "success_count": 7,
                "fail_count": 2,
            },
            {
                "name": "SSO Setup",
                "issue_type": "sso",
                "steps": "1. Verify IdP metadata URL 2. Upload SP metadata 3. Test with test account 4. Enable for org",
                "success_count": 3,
                "fail_count": 0,
            },
        ],
        "episodes": [
            {"customer": "grace_initech", "issue_type": "report_error", "product": "InitechRM",  "urgency": "high",   "status": "resolved"},
            {"customer": "grace_initech", "issue_type": "sso",          "product": "InitechSSO", "urgency": "medium", "status": "resolved"},
            {"customer": "henry_initech", "issue_type": "report_error", "product": "InitechRM",  "urgency": "low",    "status": "resolved"},
            {"customer": "ivan_initech",  "issue_type": "sso",          "product": "InitechSSO", "urgency": "high",   "status": "escalated"},
            {"customer": "ivan_initech",  "issue_type": "report_error", "product": "InitechRM",  "urgency": "medium", "status": "resolved"},
        ],
    },
}


def seed_tenant(tenant_id: str, data: dict) -> None:
    print(f"\n{'='*50}")
    print(f"  Seeding tenant: {tenant_id}")
    print(f"{'='*50}")

    graph = get_graph(tenant_id)
    ensure_indexes(tenant_id)

    # 1. Create customers
    for c in data["customers"]:
        ensure_customer(graph, c["id"], name=c["name"], plan=c["plan"])
        print(f"  ✓ Customer: {c['name']} ({c['id']})")

    # 2. Create playbooks + link to Issue type nodes
    for pb in data["playbooks"]:
        query = """
        MERGE (p:Playbook {name: $name})
        SET p.steps = $steps,
            p.success_count = $sc,
            p.fail_count = $fc
        MERGE (i:Issue {type: $itype})
        ON CREATE SET i.summary = $itype, i.status = 'template'
        MERGE (p)-[:APPLIES_TO]->(i)
        """
        graph.query(query, {
            "name": pb["name"],
            "steps": pb["steps"],
            "sc": pb["success_count"],
            "fc": pb["fail_count"],
            "itype": pb["issue_type"],
        })
        print(f"  ✓ Playbook: {pb['name']} ({pb['success_count']} wins)")

    # 3. Create historical episodes
    base_time = datetime.now(timezone.utc) - timedelta(days=30)
    for idx, ep in enumerate(data["episodes"]):
        session_id = str(uuid.uuid4())
        ep_time = (base_time + timedelta(days=idx * 5)).isoformat()

        # Create episode manually with a past timestamp
        ep_id = str(uuid.uuid4())
        query = """
        MATCH (c:Customer {id: $cid})
        CREATE (e:Episode {
            id: $eid, session_id: $sid,
            timestamp: $ts,
            transcript_summary: $summary
        })
        CREATE (c)-[:HAD_EPISODE]->(e)
        """
        summary = f"Customer reported {ep['issue_type']} on {ep['product']}. Status: {ep['status']}."
        graph.query(query, {
            "cid": ep["customer"],
            "eid": ep_id,
            "sid": session_id,
            "ts": ep_time,
            "summary": summary,
        })

        # Add user message
        append_message(graph, ep_id, role="user",
                       text=f"Hi, I'm having trouble with {ep['issue_type'].replace('_', ' ')} on {ep['product']}.")
        append_message(graph, ep_id, role="assistant",
                       text=f"I've found the best fix for this. Please follow these steps...")

        # Create issue
        issue_id = link_issue_to_episode(
            graph, ep_id, ep["issue_type"],
            f"{ep['issue_type'].replace('_', ' ').title()} on {ep['product']}",
            ep["product"], ep["urgency"]
        )

        # Record solution
        record_solution(graph, issue_id, f"Applied standard {ep['issue_type']} resolution", outcome=ep["status"])

        print(f"  ✓ Episode: {ep['customer']} / {ep['issue_type']} → {ep['status']}")

    print(f"  Tenant '{tenant_id}' seeded successfully.")


def main():
    print("🌱 Relay seed script starting...")
    for tenant_id, data in TENANTS.items():
        seed_tenant(tenant_id, data)
    print("\n✅ All tenants seeded. Open FalkorDB Browser at http://localhost:8001 to verify.")


if __name__ == "__main__":
    main()
