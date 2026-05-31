"""Active moderator + real peer Q&A + thought events, end-to-end in mock mode."""
import pytest

from backend.db.repository import InMemoryRepository
from backend.db.seed import seed_judge_panel, seed_vc_committee
from backend.engine import agent_runner, orchestrator
from backend.engine.debate import run_debate
from backend.schemas import EventType


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(agent_runner, "resolve_backend", lambda *_: None)
    monkeypatch.setattr(orchestrator, "resolve_backend", lambda *_: None)


async def test_full_mock_debate_emits_rich_interaction_events():
    repo = InMemoryRepository()
    org = seed_judge_panel(repo, "u")
    agents = repo.list_agents(org.id)
    sess = repo.create_session(org.id, "Should this win?", rounds=2)
    await run_debate(sess, agents, repo)
    events = repo.list_events(sess.id)
    types = {e.type for e in events}

    assert EventType.thought in types
    assert EventType.peer_request in types
    assert EventType.peer_response in types
    # the orchestrator moderates each executed round (not just start/continue/converge)
    assert any(e.type == EventType.orchestrator and e.content.get("action") == "moderate"
               for e in events)


async def test_peer_response_is_threaded_to_its_request():
    repo = InMemoryRepository()
    org = seed_judge_panel(repo, "u")
    agents = repo.list_agents(org.id)
    sess = repo.create_session(org.id, "Should this win?", rounds=2)
    await run_debate(sess, agents, repo)
    responses = [e for e in repo.list_events(sess.id) if e.type == EventType.peer_response]
    assert responses, "expected at least one peer to answer"
    assert all(e.parent_event for e in responses)         # threaded to the request
    assert all(e.content.get("answer") for e in responses)


async def test_vc_committee_runs_a_full_debate():
    repo = InMemoryRepository()
    org = seed_vc_committee(repo, "u")
    assert org is not None
    agents = repo.list_agents(org.id)
    assert len(agents) == 5
    sess = repo.create_session(org.id, "Should we invest?", rounds=2)
    verdict = await run_debate(sess, agents, repo)
    assert verdict.decision is not None
    assert len(verdict.influence_ranking) == len(agents)
