"""Orchestrator: weighted verdict + influence graph (ROADMAP §7.4, §8).

Numbers are REAL (scoring.py). The narrative summary is a MOCK for Hour 0 —
WS-A replaces `_summarize` with an ORCHESTRATOR_PROMPT LLM call over the transcript.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import weave

from ..schemas import (
    Agent,
    Conflict,
    Dissent,
    Event,
    EventType,
    InfluenceEdge,
    InfluenceGraph,
    InfluenceNode,
    InfluenceScore,
    Position,
    Verdict,
)
from .scoring import blended_confidence, decision_from_score, weighted_score


def _influence(agents: list[Agent], events: list[Event]):
    """Returns (ranking: list[InfluenceScore], edges: list[(from,to,weight)]).

    Hour 0: weight = count of influence mentions. TODO(WS-A): weight by |Δscore|.
    """
    out: Counter = Counter()
    edges: dict[tuple[str, str], float] = defaultdict(float)
    for ev in events:
        if ev.type == EventType.position_update and ev.influenced_by:
            for src in ev.influenced_by:
                out[src] += 1
                edges[(src, ev.agent_id)] += 1.0
    total = sum(out.values()) or 1
    ranking = [InfluenceScore(agent_id=a.id, influence=round(out.get(a.id, 0) / total, 3))
               for a in agents]
    ranking.sort(key=lambda r: r.influence, reverse=True)
    return ranking, edges


def _summarize(positions: dict[str, Position], agents: list[Agent]) -> dict:
    by_id = {a.id: a for a in agents}
    stances = [p.stance for p in positions.values()]
    majority = Counter(s.value for s in stances).most_common(1)[0][0]
    dissent = [Dissent(agent_id=aid, stance=p.stance,
                       why=f"[mock] {by_id[aid].role} stayed {p.stance.value}")
               for aid, p in positions.items() if p.stance.value != majority]
    # widest score gap = headline conflict
    ordered = sorted(positions.items(), key=lambda kv: kv[1].score)
    conflicts = []
    if len(ordered) >= 2 and ordered[-1][1].score - ordered[0][1].score >= 2:
        conflicts = [Conflict(between=[ordered[0][0], ordered[-1][0]],
                              issue="[mock] largest score gap on the panel")]
    return {
        "summary": f"[mock] Panel leans {majority}. Replace with ORCHESTRATOR_PROMPT output.",
        "key_agreements": ["[mock] agreement point"],
        "key_conflicts": conflicts,
        "dissenting_opinions": dissent,
    }


@weave.op()
async def orchestrate_verdict(agents: list[Agent], final_positions: dict[str, Position],
                              weights: dict[str, float], events: list[Event]) -> Verdict:
    scores = {aid: p.score for aid, p in final_positions.items()}
    weighted = round(weighted_score(scores, weights), 2)
    ranking, _ = _influence(agents, events)
    summary = _summarize(final_positions, agents)
    return Verdict(
        decision=decision_from_score(weighted),
        weighted_score=weighted,
        confidence=blended_confidence(list(final_positions.values())),
        influence_ranking=ranking,
        **summary,
    )


def build_influence_graph(agents: list[Agent], events: list[Event],
                          weights: dict[str, float]) -> InfluenceGraph:
    ranking, edges = _influence(agents, events)
    infl = {r.agent_id: r.influence for r in ranking}
    nodes = [InfluenceNode(agent_id=a.id, name=a.name, weight=weights.get(a.id, a.weight),
                           influence=infl.get(a.id, 0.0)) for a in agents]
    edge_models = [InfluenceEdge(**{"from": s, "to": t, "weight": w})
                   for (s, t), w in edges.items()]
    return InfluenceGraph(nodes=nodes, edges=edge_models)
