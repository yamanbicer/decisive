"""Weave scorers for the Best-of-Weave eval (ROADMAP §9.2).

Each takes a model output (a verdict dict, optionally augmented with the agents'
final `agent_scores`) and returns a float. WS-B wires these into evaluation.py.
"""
import weave

from .engine.scoring import consensus


@weave.op()
def score_confidence(output: dict) -> float:
    return float(output.get("confidence", 0.0))


@weave.op()
def score_verdict_strength(output: dict) -> float:
    return {"YES": 1.0, "CONDITIONAL": 0.5, "NO": 0.0}.get(output.get("decision"), 0.0)


@weave.op()
def score_consensus(output: dict) -> float:
    """1 = unanimous panel, 0 = maximally split. Needs `agent_scores` on the output."""
    scores = output.get("agent_scores") or []
    return consensus([float(s) for s in scores]) if scores else float(output.get("confidence", 0.0))


@weave.op()
def score_groundedness(output: dict) -> float:
    """Did agents back claims with tools? tool_calls / n_agents, capped at 1.0."""
    n = max(1, int(output.get("n_agents", 1)))
    return min(1.0, int(output.get("tool_calls", 0)) / n)


ALL_SCORERS = [score_confidence, score_verdict_strength, score_consensus, score_groundedness]
