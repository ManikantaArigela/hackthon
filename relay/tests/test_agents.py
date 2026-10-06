"""
tests/test_agents.py
Integration tests for the three agents working together.
Requires FalkorDB running + seed data loaded.
Does NOT call the LLM — mocks llm_call and llm_call_json to keep tests fast and free.

Run: pytest tests/test_agents.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid
import pytest
from unittest.mock import patch

# ─── Intake agent tests ───────────────────────────────────────────────────────

class TestIntakeAgent:

    @patch("app.agents.intake.llm_call_json")
    def test_intake_creates_episode_and_issue(self, mock_llm):
        """Intake should create an Episode + Issue node and return an IntakeResult."""
        mock_llm.return_value = {
            "issue_type": "password_reset",
            "product": "AcmeDash",
            "urgency": "high",
            "issue_summary": "Customer cannot log in due to forgotten password.",
        }

        from app.agents.intake import run
        result = run(
            tenant_id="acme",
            customer_id="alice_acme",
            customer_name="Alice",
            user_message="I forgot my password!",
            session_id=str(uuid.uuid4()),
        )

        assert result.episode_id is not None
        assert result.issue_id is not None
        assert result.issue_type == "password_reset"
        assert result.product == "AcmeDash"
        assert result.urgency == "high"

    @patch("app.agents.intake.llm_call_json")
    def test_intake_recalls_history_for_returning_customer(self, mock_llm):
        """Alice has seeded history — intake should recall it."""
        mock_llm.return_value = {
            "issue_type": "billing",
            "product": "AcmeDash",
            "urgency": "medium",
            "issue_summary": "Billing question.",
        }

        from app.agents.intake import run
        result = run(
            tenant_id="acme",
            customer_id="alice_acme",
            customer_name="Alice",
            user_message="I have a billing question",
            session_id=str(uuid.uuid4()),
        )

        # Alice has seeded episodes — history_summary should reflect that
        assert result.customer_history is not None
        assert len(result.customer_history) > 0
        assert "past episode" in result.history_summary.lower() or "episode" in result.history_summary.lower()

    @patch("app.agents.intake.llm_call_json")
    def test_intake_new_customer_gets_empty_history(self, mock_llm):
        """A brand-new customer should have no prior episodes."""
        mock_llm.return_value = {
            "issue_type": "general",
            "product": "unknown",
            "urgency": "low",
            "issue_summary": "New customer question.",
        }

        from app.agents.intake import run
        new_cid = f"new_customer_{uuid.uuid4().hex[:8]}"
        result = run(
            tenant_id="acme",
            customer_id=new_cid,
            customer_name="NewUser",
            user_message="Hello, I'm new here.",
            session_id=str(uuid.uuid4()),
        )

        assert result.customer_history == []
        assert "new customer" in result.history_summary.lower()


# ─── Resolver agent tests ─────────────────────────────────────────────────────

class TestResolverAgent:

    @patch("app.agents.resolver.llm_call")
    def test_resolver_returns_reply_and_solution(self, mock_llm):
        """Resolver should create a solution node and return a reply."""
        mock_llm.return_value = "Please try resetting your password using the link below."

        # First create an episode + issue via intake (with mocked llm)
        with patch("app.agents.intake.llm_call_json") as mock_intake_llm:
            mock_intake_llm.return_value = {
                "issue_type": "password_reset",
                "product": "AcmeDash",
                "urgency": "high",
                "issue_summary": "Password reset needed.",
            }
            from app.agents.intake import run as intake_run
            intake_result = intake_run(
                tenant_id="acme",
                customer_id="bob_acme",
                customer_name="Bob",
                user_message="I can't log in",
                session_id=str(uuid.uuid4()),
            )

        from app.agents.resolver import run as resolver_run
        result = resolver_run(
            tenant_id="acme",
            issue_type=intake_result.issue_type,
            episode_id=intake_result.episode_id,
            issue_id=intake_result.issue_id,
            history_summary=intake_result.history_summary,
        )

        assert result.reply == "Please try resetting your password using the link below."
        assert result.solution_id is not None
        assert isinstance(result.cypher_used, list)
        assert len(result.cypher_used) > 0

    @patch("app.agents.resolver.llm_call")
    def test_resolver_uses_playbook_for_known_issue(self, mock_llm):
        """For a seeded issue type, resolver should find and use a playbook."""
        mock_llm.return_value = "Here are the steps to reset your password..."

        with patch("app.agents.intake.llm_call_json") as mock_intake_llm:
            mock_intake_llm.return_value = {
                "issue_type": "password_reset",
                "product": "AcmeDash",
                "urgency": "medium",
                "issue_summary": "Password reset.",
            }
            from app.agents.intake import run as intake_run
            intake_result = intake_run(
                tenant_id="acme",
                customer_id="alice_acme",
                customer_name="Alice",
                user_message="Password reset please",
                session_id=str(uuid.uuid4()),
            )

        from app.agents.resolver import run as resolver_run
        result = resolver_run(
            tenant_id="acme",
            issue_type="password_reset",
            episode_id=intake_result.episode_id,
            issue_id=intake_result.issue_id,
            history_summary=intake_result.history_summary,
        )

        # Should have found the seeded "Reset Password" playbook
        assert result.playbook_used == "Reset Password"


# ─── Reviewer agent tests ─────────────────────────────────────────────────────

class TestReviewerAgent:

    def _create_episode_and_issue(self, tenant="acme", customer="carol_acme"):
        """Helper: run intake (mocked) to get episode+issue IDs."""
        with patch("app.agents.intake.llm_call_json") as mock_llm:
            mock_llm.return_value = {
                "issue_type": "billing",
                "product": "AcmeDash",
                "urgency": "medium",
                "issue_summary": "Billing issue.",
            }
            from app.agents.intake import run as intake_run
            return intake_run(
                tenant_id=tenant,
                customer_id=customer,
                customer_name="Carol",
                user_message="Billing problem",
                session_id=str(uuid.uuid4()),
            )

    def test_reviewer_resolved_updates_playbook(self):
        """Marking as resolved should increment the playbook's success_count."""
        from app.memory.graph import get_graph
        from app.memory.queries import find_best_playbook

        intake_r = self._create_episode_and_issue()

        # Get playbook count before
        graph = get_graph("acme")
        before = find_best_playbook(graph, "billing", limit=1)
        before_count = before[0]["success_count"] if before else 0

        from app.agents.reviewer import run as reviewer_run
        result = reviewer_run(
            tenant_id="acme",
            episode_id=intake_r.episode_id,
            issue_id=intake_r.issue_id,
            solution_id="fake_sol_id",
            playbook_name="Billing Dispute",
            outcome="resolved",
            transcript_summary="Resolved billing dispute successfully.",
        )

        assert result.outcome == "resolved"
        assert result.playbook_updated == "Billing Dispute"
        assert result.handoff_id is None
        assert result.summary_written is True

        # Playbook count should have gone up
        after = find_best_playbook(graph, "billing", limit=1)
        after_count = after[0]["success_count"] if after else 0
        assert after_count == before_count + 1

    def test_reviewer_escalated_creates_handoff_node(self):
        """Escalation should create a Handoff node in the graph."""
        intake_r = self._create_episode_and_issue()

        from app.agents.reviewer import run as reviewer_run
        result = reviewer_run(
            tenant_id="acme",
            episode_id=intake_r.episode_id,
            issue_id=intake_r.issue_id,
            solution_id="fake_sol_id",
            playbook_name="Billing Dispute",
            outcome="escalated",
        )

        assert result.outcome == "escalated"
        assert result.handoff_id is not None

        # Verify handoff node exists in graph
        from app.memory.graph import get_graph
        graph = get_graph("acme")
        res = graph.query(
            "MATCH (h:Handoff {id: $hid}) RETURN h.status",
            {"hid": result.handoff_id}
        )
        assert len(res.result_set) == 1


# ─── Orchestrator end-to-end test ─────────────────────────────────────────────

class TestOrchestrator:

    @patch("app.agents.resolver.llm_call")
    @patch("app.agents.intake.llm_call_json")
    def test_full_pipeline_returns_reply_and_explain(self, mock_intake, mock_resolver):
        """Full Intake → Resolver pipeline should return reply + explain dict."""
        mock_intake.return_value = {
            "issue_type": "login_error",
            "product": "AcmeAPI",
            "urgency": "high",
            "issue_summary": "Login error on API.",
        }
        mock_resolver.return_value = "Try clearing your browser cache and logging in again."

        from app import orchestrator
        result = orchestrator.chat(
            tenant_id="acme",
            customer_id="bob_acme",
            customer_name="Bob",
            user_message="I can't log in to AcmeAPI!",
        )

        assert "reply" in result
        assert result["reply"] == "Try clearing your browser cache and logging in again."
        assert "explain" in result
        explain = result["explain"]
        assert "episode_id" in explain
        assert "issue_type" in explain
        assert explain["issue_type"] == "login_error"
        assert "cypher_used" in explain
        assert "agent_pipeline" in explain
        assert "Intake" in explain["agent_pipeline"]
        assert "Resolver" in explain["agent_pipeline"]
