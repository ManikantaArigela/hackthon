"""
scripts/load_test.py
Concurrency load test — runs N parallel chat sessions against the FastAPI backend.
Proves the system can handle concurrent reads/writes to FalkorDB without errors.

Usage:
    python scripts/load_test.py --sessions 20 --base-url http://localhost:8000

Pass condition: all sessions complete, zero errors, average latency < 10s.
"""

import asyncio
import argparse
import time
import json
import sys
import os
from dataclasses import dataclass, field

import httpx

# ─── Test scenarios ───────────────────────────────────────────────────────────

SCENARIOS = [
    {"tenant_id": "acme",    "customer_id": "alice_acme",   "customer_name": "Alice",
     "message": "Hi, I forgot my password and can't log in to AcmeDash."},
    {"tenant_id": "acme",    "customer_id": "bob_acme",     "customer_name": "Bob",
     "message": "I'm getting a login error on AcmeAPI — says invalid credentials."},
    {"tenant_id": "acme",    "customer_id": "carol_acme",   "customer_name": "Carol",
     "message": "I was charged twice for my subscription this month."},
    {"tenant_id": "globex",  "customer_id": "dan_globex",   "customer_name": "Dan",
     "message": "My API key stopped working after I rotated it last week."},
    {"tenant_id": "globex",  "customer_id": "eve_globex",   "customer_name": "Eve",
     "message": "Queries on GlobexDB are extremely slow today."},
    {"tenant_id": "initech", "customer_id": "grace_initech","customer_name": "Grace",
     "message": "The TPS report is throwing an error when I run it."},
    {"tenant_id": "initech", "customer_id": "henry_initech","customer_name": "Henry",
     "message": "SSO login is broken — redirect loop after authentication."},
]


@dataclass
class SessionResult:
    session_index: int
    tenant_id: str
    customer_id: str
    success: bool
    latency_s: float
    error: str = ""
    reply_length: int = 0


# ─── Single session ───────────────────────────────────────────────────────────

async def run_session(client: httpx.AsyncClient, base_url: str,
                      session_index: int, scenario: dict) -> SessionResult:
    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/chat",
            json={
                "tenant_id": scenario["tenant_id"],
                "customer_id": scenario["customer_id"],
                "customer_name": scenario["customer_name"],
                "message": scenario["message"],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        latency = time.perf_counter() - start
        reply = data.get("reply", "")
        return SessionResult(
            session_index=session_index,
            tenant_id=scenario["tenant_id"],
            customer_id=scenario["customer_id"],
            success=True,
            latency_s=round(latency, 2),
            reply_length=len(reply),
        )
    except Exception as e:
        latency = time.perf_counter() - start
        return SessionResult(
            session_index=session_index,
            tenant_id=scenario["tenant_id"],
            customer_id=scenario["customer_id"],
            success=False,
            latency_s=round(latency, 2),
            error=str(e),
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(n_sessions: int, base_url: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Relay Load Test — {n_sessions} parallel sessions")
    print(f"  Target: {base_url}")
    print(f"{'='*60}\n")

    # Build session list (cycle through scenarios)
    sessions = [
        (i, SCENARIOS[i % len(SCENARIOS)])
        for i in range(n_sessions)
    ]

    async with httpx.AsyncClient() as client:
        start_wall = time.perf_counter()
        tasks = [
            run_session(client, base_url, idx, scenario)
            for idx, scenario in sessions
        ]
        results: list[SessionResult] = await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - start_wall

    # ─── Report ───────────────────────────────────────────────────────────────
    successes = [r for r in results if r.success]
    failures  = [r for r in results if not r.success]
    latencies = [r.latency_s for r in successes]
    avg_lat   = round(sum(latencies) / len(latencies), 2) if latencies else 0
    max_lat   = round(max(latencies), 2) if latencies else 0
    min_lat   = round(min(latencies), 2) if latencies else 0

    print(f"{'─'*60}")
    print(f"  Sessions:        {n_sessions}")
    print(f"  Successes:       {len(successes)}")
    print(f"  Failures:        {len(failures)}")
    print(f"  Wall time:       {round(wall_time, 2)}s")
    print(f"  Avg latency:     {avg_lat}s")
    print(f"  Min latency:     {min_lat}s")
    print(f"  Max latency:     {max_lat}s")
    print(f"{'─'*60}")

    if failures:
        print("\n  FAILURES:")
        for r in failures:
            print(f"    [session {r.session_index}] {r.tenant_id}/{r.customer_id}: {r.error}")

    # ─── Save results to JSON ─────────────────────────────────────────────────
    out = {
        "sessions": n_sessions,
        "successes": len(successes),
        "failures": len(failures),
        "wall_time_s": round(wall_time, 2),
        "avg_latency_s": avg_lat,
        "min_latency_s": min_lat,
        "max_latency_s": max_lat,
        "results": [
            {
                "session": r.session_index,
                "tenant": r.tenant_id,
                "customer": r.customer_id,
                "success": r.success,
                "latency_s": r.latency_s,
                "error": r.error,
            }
            for r in results
        ],
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "load_test_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved to load_test_results.json")

    # ─── Pass/fail ────────────────────────────────────────────────────────────
    passed = len(failures) == 0 and avg_lat < 10
    if passed:
        print("\n✅ LOAD TEST PASSED — no errors, avg latency under 10s\n")
    else:
        print("\n❌ LOAD TEST FAILED\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Relay load test")
    parser.add_argument("--sessions",  type=int, default=20,                     help="Number of parallel sessions")
    parser.add_argument("--base-url",  type=str, default="http://localhost:8000", help="FastAPI base URL")
    args = parser.parse_args()
    asyncio.run(main(args.sessions, args.base_url))
