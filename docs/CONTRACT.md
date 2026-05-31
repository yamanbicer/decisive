# The Frozen Contract (Hour 0)

This is the seam between all four workstreams. **Source of truth:** `backend/schemas.py`
(Python) ↔ `frontend/lib/types.ts` (TypeScript). Change a field → announce it in the team channel and update both.

## Event taxonomy (`events.type` → `content`)
| type | by | content |
|---|---|---|
| `position` | agent | `{stance, score, confidence, rationale}` (round 0) |
| `thought` | agent | `{text}` |
| `message` | agent | `{text, to:"all"}` ← **this is what voice speaks** |
| `peer_request` | agent | `{to_agent_id, question}` |
| `peer_response` | agent | `{to_agent_id, answer}` (parent_event = request) |
| `tool_call` | agent | `{tool, args}` |
| `tool_result` | agent | `{tool, result}` (parent_event = call) |
| `position_update` | agent | `{stance, score, confidence, rationale}` + `influenced_by:[agent_id]` |
| `orchestrator` | orchestrator | `{action:"start"|"continue"|"converge", conflict_level?}` |
| `verdict` | orchestrator | the Verdict object (below) |
| `error` | system | `{error}` |

Every event also has: `id, session_id, seq (global order), round, agent_id?, parent_event?, influenced_by[]`.

## Verdict
```
{ decision: YES|NO|CONDITIONAL, weighted_score: 0..10, confidence: 0..1, summary,
  key_agreements: [str], key_conflicts: [{between:[id], issue}],
  dissenting_opinions: [{agent_id, stance, why}], influence_ranking: [{agent_id, influence}] }
```

## API (base `http://localhost:8000`, Bearer Supabase JWT; dev allows no token)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ok, weave, supabase, auth, repo}` |
| GET | `/orgs` | — | `[Org]` |
| POST | `/orgs` | `{name, description?, preset?}` | `Org` |
| POST | `/orgs/generate` | `{prompt}` | `Org` |
| GET | `/orgs/{id}/agents` | — | `[Agent]` |
| POST | `/orgs/{id}/agents` | `AgentCreate` | `Agent` |
| PATCH | `/agents/{id}` | `AgentUpdate` | `Agent` |
| POST | `/sessions` | `{org_id, question, context?, rounds?}` | `{session_id}` |
| GET | `/sessions/{id}` | — | `{session, events, positions, verdict}` |
| GET | `/sessions/{id}/stream` | SSE | `event:<type> data:<event json>` (replays history then goes live; ends with `event:done`) |
| POST | `/sessions/{id}/rerun` | `{weights_override?, context?}` | `{session_id}` (child session) |
| GET | `/sessions/{id}/influence` | — | `{nodes:[{agent_id,name,weight,influence}], edges:[{from,to,weight}]}` |

## Streaming
The engine `publish()`es each event to in-process subscribers; `/stream` drains them as SSE.
Voice (WS-D) and the frontend (WS-C) both subscribe to the same endpoint. Swap for Supabase
Realtime on the `events` table if you need cross-process fan-out.
