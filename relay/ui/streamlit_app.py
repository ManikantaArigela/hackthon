"""
ui/streamlit_app.py
Relay Chat UI — Streamlit frontend.

Layout:
  Sidebar:  tenant picker, customer picker
  Main:     chat window
  Right:    Explain panel (Cypher, nodes, playbook, agent pipeline)
"""

import requests
import streamlit as st

API_BASE = "http://localhost:8000"

TENANTS = {
    "acme": {
        "alice_acme": "Alice",
        "bob_acme": "Bob",
        "carol_acme": "Carol",
    },
    "globex": {
        "dan_globex": "Dan",
        "eve_globex": "Eve",
        "frank_globex": "Frank",
    },
    "initech": {
        "grace_initech": "Grace",
        "henry_initech": "Henry",
        "ivan_initech": "Ivan",
    },
}

st.set_page_config(
    page_title="Relay — Graph-Memory Support Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔁 Relay")
    st.caption("Graph-Memory Support Agent")
    st.divider()

    tenant_id = st.selectbox("🏢 Tenant", list(TENANTS.keys()))
    customers = TENANTS[tenant_id]
    customer_id = st.selectbox("👤 Customer", list(customers.keys()),
                                format_func=lambda k: customers[k])
    customer_name = customers[customer_id]

    st.divider()
    st.caption("Each tenant has its own isolated FalkorDB graph.")

# ─── Session state ────────────────────────────────────────────────────────────
session_key = f"{tenant_id}_{customer_id}"
if "chats" not in st.session_state:
    st.session_state.chats = {}
if session_key not in st.session_state.chats:
    st.session_state.chats[session_key] = {
        "messages": [],
        "last_explain": None,
        "last_episode_id": None,
        "last_issue_id": None,
        "last_solution_id": None,
        "last_playbook": None,
        "session_id": None,
    }

chat_state = st.session_state.chats[session_key]

# ─── Layout ───────────────────────────────────────────────────────────────────
chat_col, explain_col = st.columns([2, 1])

# ─── Chat column ──────────────────────────────────────────────────────────────
with chat_col:
    st.header(f"💬 Chat — {customer_name} @ {tenant_id.upper()}")

    # Display message history
    for msg in chat_state["messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    user_input = st.chat_input("Type your message...")
    if user_input:
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)
        chat_state["messages"].append({"role": "user", "content": user_input})

        # Call backend
        with st.spinner("Relay agents thinking..."):
            try:
                resp = requests.post(f"{API_BASE}/chat", json={
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "message": user_input,
                    "session_id": chat_state["session_id"],
                }, timeout=30)
                data = resp.json()

                reply = data.get("reply", "Sorry, something went wrong.")
                explain = data.get("explain", {})

                # Update state
                chat_state["session_id"] = data.get("session_id")
                chat_state["last_explain"] = explain
                chat_state["last_episode_id"] = explain.get("episode_id")
                chat_state["last_issue_id"] = explain.get("issue_id")
                chat_state["last_solution_id"] = explain.get("solution_id")
                chat_state["last_playbook"] = explain.get("playbook_used")

                with st.chat_message("assistant"):
                    st.write(reply)
                chat_state["messages"].append({"role": "assistant", "content": reply})

            except Exception as e:
                st.error(f"Backend error: {e}")

    # Outcome buttons (show after at least one AI reply)
    if chat_state["last_episode_id"]:
        st.divider()
        st.caption("Did this resolve your issue?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Resolved", use_container_width=True):
                requests.post(f"{API_BASE}/outcome", json={
                    "tenant_id": tenant_id,
                    "episode_id": chat_state["last_episode_id"],
                    "issue_id": chat_state["last_issue_id"],
                    "solution_id": chat_state["last_solution_id"],
                    "playbook_name": chat_state["last_playbook"],
                    "outcome": "resolved",
                    "transcript_summary": f"Resolved via {chat_state['last_playbook'] or 'manual'}",
                }, timeout=10)
                st.success("Marked as resolved! Playbook stats updated. 📊")
        with col2:
            if st.button("❌ Escalate", use_container_width=True):
                requests.post(f"{API_BASE}/outcome", json={
                    "tenant_id": tenant_id,
                    "episode_id": chat_state["last_episode_id"],
                    "issue_id": chat_state["last_issue_id"],
                    "solution_id": chat_state["last_solution_id"],
                    "playbook_name": chat_state["last_playbook"],
                    "outcome": "escalated",
                    "transcript_summary": "Escalated — unresolved after AI attempt",
                }, timeout=10)
                st.warning("Escalated. A Handoff node has been created in the graph. 🔄")

# ─── Explain panel ────────────────────────────────────────────────────────────
with explain_col:
    st.header("🔍 Explain")
    explain = chat_state.get("last_explain")

    if not explain:
        st.info("Send a message to see the graph path behind the answer.")
    else:
        st.subheader("📌 Entities Extracted")
        st.write(f"**Issue type:** `{explain.get('issue_type', '—')}`")
        st.write(f"**Product:** `{explain.get('product', '—')}`")
        st.write(f"**Urgency:** `{explain.get('urgency', '—')}`")
        st.write(f"**History:** {explain.get('history_summary', '—')}")

        st.divider()
        st.subheader("📚 Playbook Used")
        playbook = explain.get("playbook_used")
        if playbook:
            st.success(f"**{playbook}**")
        else:
            st.warning("No matching playbook found")

        st.divider()
        st.subheader("🤖 Agent Pipeline")
        for agent in explain.get("agent_pipeline", []):
            st.write(f"→ **{agent}**")

        st.divider()
        st.subheader("🗃️ Nodes Touched")
        for node in explain.get("nodes_touched", []):
            st.code(node, language=None)

        st.divider()
        st.subheader("📝 Cypher Queries Used")
        for q in explain.get("cypher_used", []):
            st.code(q, language="cypher")

        st.divider()
        st.subheader("🔗 Episode ID")
        st.code(explain.get("episode_id", "—"), language=None)

    # Graph visualization
    st.divider()
    st.subheader("🕸️ Customer Graph")
    if st.button("Load graph nodes"):
        try:
            r = requests.get(f"{API_BASE}/graph/{tenant_id}/{customer_id}", timeout=10)
            nodes = r.json().get("nodes", [])
            if nodes:
                st.dataframe(nodes, use_container_width=True)
            else:
                st.info("No episodes yet for this customer.")
        except Exception as e:
            st.error(f"Could not load graph: {e}")
