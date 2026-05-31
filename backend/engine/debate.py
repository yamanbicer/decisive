"""The debate loop (ROADMAP §7.2). Persists every step as an event, streams it
live, and is fully traced by Weave. Agent bodies (incl. the ReAct tool loop) live
in agent_runner.py; this module owns the round structure, event emission, the
compact board, the per-agent evidence ledger, the peer-response sub-turn, and the
between-round moderator."""
from __future__ import annotations

import asyncio
from typing import Optional

import weave

from ..config import get_settings
from ..schemas import Agent, EventType, Position, Session, SessionStatus, Verdict
from . import stream
from .agent_runner import agent_answer_peer, agent_position, agent_turn
from .budget import pack_lines
from .mcp_manager import ensure_mcp_registered
from .orchestrator import moderate_round, orchestrate_verdict
from .scoring import normalized_variance
from .tool_registry import default_registry

CONVERGE_THRESHOLD = 0.15  # normalized score variance below which we stop early


def _short_role(role: str) -> str:
    return role.split("—")[0].strip()[:42]


def _render_board(positions: dict[str, Position], agents: list[Agent],
                  prev: Optional[dict[str, Position]] = None) -> str:
    """Compact board: one whole line per agent (stance/score/confidence + Δ since
    last round + current rationale), packed under the char budget so multi-round
    debates don't grow the prompt without bound."""
    by_id = {a.id: a for a in agents}
    rows: list[str] = []
    for aid, p in positions.items():
        a = by_id.get(aid)
        if not a:
            continue
        delta = ""
        if prev and aid in prev:
            d = round(p.score - prev[aid].score, 1)
            if abs(d) >= 0.1:
                delta = f" ({'+' if d > 0 else ''}{d})"
        rows.append(f"- {a.name} ({_short_role(a.role)}): {p.stance.value} {p.score}/10 "
                    f"conf {p.confidence}{delta} — {p.rationale}")
    return pack_lines(rows, get_settings().board_char_budget, keep="head")


def _conflict_pairs(agents: list[Agent]) -> list[tuple[str, str, str]]:
    """Declared (conflict_partner) pairs present in the panel, de-duplicated."""
    present = {a.id for a in agents}
    pairs: list[tuple[str, str, str]] = []
    seen: set[frozenset] = set()
    for a in agents:
        cp = getattr(a, "conflict_partner", None)
        if cp and cp in present:
            key = frozenset((a.id, cp))
            if key not in seen:
                seen.add(key)
                pairs.append((a.id, cp, getattr(a, "conflict_dimension", "") or ""))
    return pairs


@weave.op()
async def run_debate(session: Session, agents: list[Agent], repo,
                     weights: Optional[dict[str, float]] = None) -> Verdict:
    weights = weights or session.weights_override or {a.id: a.weight for a in agents}
    by_id = {a.id: a for a in agents}

    # Make any configured MCP tools available before agents take a turn (no-op if none).
    try:
        await ensure_mcp_registered(default_registry())
    except Exception:
        pass

    def emit(round, etype, content, agent_id=None, parent=None, influenced=None):
        ev = repo.append_event(session.id, round, etype, content, agent_id=agent_id,
                               parent_event=parent, influenced_by=influenced)
        stream.publish(session.id, ev.model_dump(mode="json"))
        return ev

    repo.update_session(session.id, status=SessionStatus.running)
    emit(0, EventType.orchestrator, {"action": "start", "question": session.question})

    # ── Round 0: independent positions (parallel) ──
    positions: dict[str, Position] = {}
    results = await asyncio.gather(
        *[agent_position(a, session.question, session.context) for a in agents])
    for a, p in zip(agents, results):
        positions[a.id] = p
        repo.save_position(session.id, 0, a.id, p)
        emit(0, EventType.position, p.model_dump(), agent_id=a.id)

    conflict_pairs = _conflict_pairs(agents)
    evidence: dict[str, list[dict]] = {a.id: [] for a in agents}  # carried across rounds
    pending_directive = ""

    # ── Rounds 1..N: debate ──
    for rnd in range(1, session.rounds + 1):
        conflict = round(normalized_variance([p.score for p in positions.values()]), 3)
        emit(rnd, EventType.orchestrator, {"action": "continue", "conflict_level": conflict})
        if conflict < CONVERGE_THRESHOLD and rnd > 1:
            emit(rnd, EventType.orchestrator, {"action": "converge", "conflict_level": conflict})
            break

        board = _render_board(positions, agents)
        if pending_directive:
            board = f"MODERATOR DIRECTIVE: {pending_directive}\n\n{board}"

        prev = dict(positions)
        turns = await asyncio.gather(*[
            agent_turn(a, positions[a.id], board, agents, rnd,
                       emit=emit, session_id=session.id, evidence=evidence[a.id])
            for a in agents])

        pending_requests: list[tuple[Agent, dict, object]] = []
        for a, t in zip(agents, turns):
            if t.thought:
                emit(rnd, EventType.thought, {"text": t.thought}, agent_id=a.id)
            emit(rnd, EventType.message, {"text": t.message, "to": "all"}, agent_id=a.id)
            if t.peer_request:
                req_ev = emit(rnd, EventType.peer_request, t.peer_request, agent_id=a.id)
                pending_requests.append((a, t.peer_request, req_ev))
            delta = round(t.position.score - positions[a.id].score, 2)
            emit(rnd, EventType.position_update, {**t.position.model_dump(), "delta": delta},
                 agent_id=a.id, influenced=t.influenced_by)
            repo.save_position(session.id, rnd, a.id, t.position)
            positions[a.id] = t.position

        # ── peer-response sub-turn: a directly-asked peer actually answers ──
        for asker, pr, req_ev in pending_requests:
            target = by_id.get(pr.get("to_agent_id"))
            if not target:
                continue
            answer = await agent_answer_peer(target, pr.get("question", ""), asker.name)
            emit(rnd, EventType.peer_response,
                 {"answer": answer, "to_agent_id": asker.id, "question": pr.get("question", "")},
                 agent_id=target.id, parent=getattr(req_ev, "id", None))
            # the asker sees the answer in their evidence ledger next round (causal influence)
            evidence[asker.id].append({"tool": f"peer:{target.name}", "result": {"text": answer}})

        # ── between-round moderator: name the tension, direct the next round ──
        mod = await moderate_round(agents, prev, positions, rnd, conflict_pairs)
        emit(rnd, EventType.orchestrator, mod)
        pending_directive = mod.get("directive", "")

    # ── Verdict ──
    events = repo.list_events(session.id)
    verdict = await orchestrate_verdict(agents, positions, weights, events)
    weave_url = None
    try:
        call = weave.get_current_call()
        weave_url = getattr(call, "ui_url", None)
    except Exception:
        pass
    emit(session.rounds + 1, EventType.verdict, verdict.model_dump())
    repo.update_session(session.id, status=SessionStatus.done,
                        final_verdict=verdict, weave_trace_url=weave_url)
    stream.close(session.id)
    return verdict
