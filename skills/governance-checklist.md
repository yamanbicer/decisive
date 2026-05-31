---
name: governance-checklist
description: Operating-model, accountability, and risk checklist for adopting a system.
---

## Governance & Accountability Checklist

For a decision/AI system to be adopted in a real organization, it must answer:

1. **Accountability** — When the system is wrong, WHO is answerable, and how is that
   traced? A defensible verdict names an owner, not just a score.
2. **Auditability** — Can every output be reconstructed from inputs? Is there a
   durable, inspectable lineage (events, traces) a regulator could follow?
3. **Override & control** — Can a human inspect, challenge, and override with
   authority — and is that override itself recorded?
4. **Failure modes** — What happens on bad input, a model outage, or disagreement?
   Graceful degradation beats silent failure.
5. **Change management** — How are weights/policies versioned and approved? Who signs
   off on a change to the decision logic?
6. **Data & privacy** — What data enters the system, where does it live, who can see it.

## How to apply
Hold the project to the standard of a system you'd actually put in front of a board.
Demand evidence of lineage and override authority; if it's a controlled demo with no
accountability story, that caps your confidence even if the output looks good.
