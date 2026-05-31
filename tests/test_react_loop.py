"""The ReAct loop: an agent calls a tool, sees the result, and revises its score."""
from backend.engine import agent_runner
from backend.schemas import Agent, EventType, Position, Stance


def _agent():
    return Agent(id="a", org_id="o", name="A", role="r", system_prompt="",
                 tools=["market_research"])


def _collector():
    events = []

    def emit(rnd, etype, content, agent_id=None, parent=None, influenced=None):
        events.append((etype, content))
        return type("E", (), {"id": f"e{len(events)}"})()

    return events, emit


async def test_react_loop_changes_position(monkeypatch):
    calls = {"n": 0}

    async def fake_complete_json(backend, model, system, prompt, schema):
        calls["n"] += 1
        if calls["n"] == 1:                       # first pass: request a tool
            return {"thought": "check the market", "message": "",
                    "tool_call": {"tool": "market_research", "args": {"company": "Acme"}},
                    "position": {"stance": "CONDITIONAL", "score": 5.0, "confidence": 0.6,
                                 "rationale": "before evidence"},
                    "influenced_by": []}
        return {"message": "the evidence convinced me", "tool_call": None,  # finalize
                "position": {"stance": "YES", "score": 8.0, "confidence": 0.85,
                             "rationale": "market is real (per tool)"},
                "influenced_by": []}

    monkeypatch.setattr(agent_runner, "resolve_backend", lambda *_: "wandb")
    monkeypatch.setattr(agent_runner, "complete_json", fake_complete_json)
    events, emit = _collector()
    prev = Position(stance=Stance.CONDITIONAL, score=5.0, confidence=0.6, rationale="")
    res = await agent_runner.agent_turn(_agent(), prev, "board", [], 1,
                                        emit=emit, session_id="s", evidence=[])
    assert res.position.score == 8.0 and res.position.stance == Stance.YES
    types = [t for t, _ in events]
    assert EventType.tool_call in types and EventType.tool_result in types


async def test_react_loop_respects_k_cap(monkeypatch):
    async def always_tool(*a, **k):
        return {"message": "", "tool_call": {"tool": "market_research", "args": {"company": "X"}},
                "position": {"stance": "CONDITIONAL", "score": 5.0, "confidence": 0.5,
                             "rationale": ""}, "influenced_by": []}

    monkeypatch.setattr(agent_runner, "resolve_backend", lambda *_: "wandb")
    monkeypatch.setattr(agent_runner, "complete_json", always_tool)
    events, emit = _collector()
    prev = Position(stance=Stance.CONDITIONAL, score=5.0, confidence=0.5, rationale="")
    await agent_runner.agent_turn(_agent(), prev, "b", [], 1,
                                  emit=emit, session_id="s", evidence=[], max_calls=2)
    tool_results = [t for t, _ in events if t == EventType.tool_result]
    assert len(tool_results) == 2   # capped at k, then forced to finalize
