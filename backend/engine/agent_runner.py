"""One agent's turn (ROADMAP §7.3).

HOUR 0 = deterministic MOCK so the whole pipeline runs end-to-end with no API
keys. WS-A replaces the mock bodies with real Claude Agent SDK / W&B Inference
calls returning AGENT_TURN_SCHEMA — the function signatures and return shapes
stay identical, so nothing downstream changes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import weave

from ..schemas import Agent, Position, Provider, Stance
from .scoring import decision_from_score


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


@dataclass
class TurnResult:
    message: str
    position: Position
    influenced_by: list[str] = field(default_factory=list)
    peer_request: Optional[dict] = None      # {"to_agent_id","question"}
    tool_call: Optional[dict] = None          # {"tool","args"}


# ───────────────────────────── round 0 ─────────────────────────────
@weave.op()
async def agent_position(agent: Agent, question: str, context: Optional[str]) -> Position:
    """Initial independent position. MOCK → replace with a single SDK call."""
    r = _seed(agent.name, question)
    score = round(4.0 + (r % 60) / 10.0, 1)          # 4.0 .. 9.9
    return Position(
        stance=decision_from_score(score),
        score=score,
        confidence=round(0.5 + (r % 40) / 100.0, 2),  # 0.50 .. 0.89
        rationale=f"[mock] {agent.role}: initial read before hearing the others.",
    )


# ───────────────────────────── rounds 1..N ─────────────────────────────
@weave.op()
async def agent_turn(agent: Agent, prev: Position, board: str,
                     peers: list[Agent], rnd: int) -> TurnResult:
    """One deliberation turn. MOCK → replace with an SDK call using DEBATE_RUBRIC
    + AGENT_TURN_SCHEMA, with peers' positions in `board` and MCP tools attached."""
    r = _seed(agent.name, str(rnd))
    # Mock "deliberation": nudge score toward the room (consensus pull), note an influencer.
    pull = (6.5 - prev.score) * 0.25
    new_score = max(0.0, min(10.0, round(prev.score + pull, 1)))
    influenced = []
    if peers and abs(pull) > 0.4:
        influencer = peers[r % len(peers)]
        if influencer.id != agent.id:
            influenced = [influencer.id]
    return TurnResult(
        message=f"[mock] {agent.name}: after round {rnd} I "
                f"{'hold' if abs(pull) < 0.4 else 'adjust'} my position.",
        position=Position(
            stance=decision_from_score(new_score),
            score=new_score,
            confidence=min(1.0, round(prev.confidence + 0.05, 2)),
            rationale=f"[mock] {agent.role}: updated after the debate.",
        ),
        influenced_by=influenced,
    )


# ─────────────── real-call skeletons (WS-A wires these in H1-H2) ───────────────
async def _call_anthropic(agent: Agent, system: str, prompt: str, schema: dict) -> dict:
    """TODO(WS-A): Claude Agent SDK — subagent with `agent.system_prompt` + MCP tools.
    from claude_agent_sdk import query  # see code.claude.com/docs/en/agent-sdk
    Return parsed JSON matching AGENT_TURN_SCHEMA.
    """
    raise NotImplementedError


async def _call_wandb_inference(agent: Agent, system: str, prompt: str, schema: dict) -> dict:
    """TODO(WS-A): OpenAI-compatible call to W&B Inference for `provider=wandb` agents.
    Reuse the client pattern from the repo-root main.py (base_url + project header).
    """
    raise NotImplementedError
