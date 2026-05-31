# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Decision Harness** — a configurable AI decision council. A panel of weighted persona-agents (judges / a board / a VC committee) debates a question over N rounds and produces a **weighted, fully-inspectable verdict** plus an **influence graph** showing who swayed whom. Every step is emitted as a typed event, streamed live, and traced in W&B Weave.

The authoritative product spec is [ROADMAP.md](ROADMAP.md); [START_HERE.md](START_HERE.md) is the orientation doc; [docs/CONTRACT.md](docs/CONTRACT.md) is the API/event contract.

## Repo layout

- [backend/](backend/) — FastAPI app, the debate engine, repositories, eval harness. **This is the product.**
- [frontend/](frontend/) — Next.js 16 / React 18 boardroom UI (SSE-driven).
- [voice/](voice/) — ElevenLabs TTS bridge (stretch goal, mostly stubs).
- [personas/](personas/) — `*.md` persona files that seed the demo "Judge Panel" org.
- [jury-meeting/](jury-meeting/) — a **separate, standalone package** (its own backend + single-file frontend). It only couples to the main app by *reading* a finished decision from Supabase; it shares no engine code. Changes here don't affect the main app.
- [main.py](main.py) — root-level Weave + W&B Inference smoke test, unrelated to the backend app (`python main.py`).

## Central design principle: graceful degradation

**The entire stack boots and runs end-to-end with zero API keys.** This is the most important constraint to preserve — never make a code path hard-require a key.

- No Supabase configured → `InMemoryRepository`, auto-seeded with the Judge Panel ([backend/db/repository.py](backend/db/repository.py), [backend/db/seed.py](backend/db/seed.py)).
- No model keys → agents and the orchestrator summary fall back to **deterministic mocks** ([backend/engine/agent_runner.py](backend/engine/agent_runner.py)).
- No `WANDB_API_KEY` → Weave tracing silently off.
- Auth: a missing token is the demo user **only** in local dev; the moment `SUPABASE_URL` is set, a valid Bearer token is required ([backend/api/deps.py](backend/api/deps.py)).

`get_settings()` ([backend/config.py](backend/config.py)) reads `backend/.env` (resolved by absolute path, so it works regardless of launch CWD) and exposes `*_enabled` properties that gate every optional subsystem.

## Architecture

### The frozen contract
[backend/schemas.py](backend/schemas.py) (Pydantic) ↔ [frontend/lib/types.ts](frontend/lib/types.ts) (TypeScript), documented in [docs/CONTRACT.md](docs/CONTRACT.md). These are the seam between backend, frontend, and voice. **Do not rename a field on one side without updating the other and the contract doc.**

### Event-sourced debate
The whole debate is a stream of typed `Event`s (`position`, `message`, `peer_request`, `tool_call`/`tool_result`, `position_update` with `influenced_by`, `orchestrator`, `verdict`). State (boardroom, transcript, verdict, influence) is **reconstructed by replaying events** — on the backend, the frontend ([frontend/lib/useEventStream.ts](frontend/lib/useEventStream.ts)), and the voice bridge alike. The taxonomy is the table in [docs/CONTRACT.md](docs/CONTRACT.md).

### Debate loop — [backend/engine/debate.py](backend/engine/debate.py)
1. **Round 0**: every agent forms an independent position in parallel (`asyncio.gather`).
2. **Rounds 1..N**: each agent takes a turn seeing a **compact board** (a stance/score table + latest rationales + Δ since last round, packed to a char budget — [budget.py](backend/engine/budget.py)). The turn is a **bounded ReAct loop** ([agent_runner.py](backend/engine/agent_runner.py) `agent_turn`): the agent may call a tool from its allowlist, see the result in an **evidence ledger**, and REVISE its message + position before finalizing (cap `TOOL_MAX_CALLS`). It emits an optional `thought`, a message, optional peer_request / tool_call(s), and a position_update carrying `influenced_by`. A directly-asked peer actually answers via a `peer_response` sub-turn (`agent_answer_peer`), which the asker sees next round. After each round the orchestrator **moderates** (`moderate_round`): names who moved, computes conflict, and emits a directive pitting conflict-partners against each other. Early-converges when normalized score variance drops below `CONVERGE_THRESHOLD` (0.15).
3. **Verdict** ([backend/engine/orchestrator.py](backend/engine/orchestrator.py)): the weighted score, conflicts, and dissent are computed with **real, deterministic math** ([backend/engine/scoring.py](backend/engine/scoring.py)); only the natural-language `summary` comes from an LLM (with a terse fallback). Influence ranking is derived from `position_update.influenced_by` edges.

Every engine function is decorated `@weave.op()` so the full debate auto-traces (incl. each tool call nested under its agent's turn).

### Agent tools, skills & live MCP — [tool_registry.py](backend/engine/tool_registry.py)
`agent.tools` (a per-agent allowlist) is finally **wired**: `default_registry()` holds `ToolSpec`s (web research in [web_research.py](backend/engine/web_research.py): `web_search`/`fetch_url` + `market_research`/`competitor_scan`/`product_research`; `use_skill`; `research` is a kept alias → `web_search`). `execute_tool(tool, args, ctx)` ([tools.py](backend/engine/tools.py)) enforces the allowlist (`research` etc. only for agents that declare them; `use_skill` only when the agent has `skills`), routes by kind, and is timeout-guarded — a failure returns an `{"error":…}` dict, never raises. The agent prompt injects only that agent's tool **manifest** so the model knows what it has. **Web backends degrade to a deterministic mock with no `FIRECRAWL_API_KEY`/`TAVILY_API_KEY`.** **Skills** ([skills.py](backend/engine/skills.py)) are `skills/*.md` rubrics: a short manifest is always in-prompt, the full body loads only when `use_skill(name)` is called (progressive disclosure). **Live MCP** ([mcp_manager.py](backend/engine/mcp_manager.py)) is opt-in via `MCP_CONFIG_PATH` → [mcp_servers.json](mcp_servers.json); it surfaces external MCP tools (e.g. the W&B/Weave MCP as `weave_query`, given to Nicolas) through the same registry. Connections are **per-call** (a fresh nested-`async with` session inside the calling task — see Gotchas).

### Provider routing — [backend/engine/llm.py](backend/engine/llm.py)
`resolve_backend(provider)` picks the actual backend: `"wandb"` (W&B Inference, OpenAI-compatible async client, JSON mode) | `"anthropic"` (Messages API with **forced tool-use** to guarantee structured JSON) | `None` (→ caller uses its mock). If an agent's declared provider has no creds, it falls back to whatever IS configured. All structured calls go through `complete_json(...)`.

### Streaming — [backend/engine/stream.py](backend/engine/stream.py) + [backend/api/sessions.py](backend/api/sessions.py)
In-process `asyncio.Queue` pub/sub. `POST /sessions` kicks off the debate as a background `asyncio.create_task`; `GET /sessions/{id}/stream` is an SSE endpoint that **replays event history, then goes live**. For multi-process deploys this would be swapped for Supabase Realtime on the `events` table.

### Repository pattern — [backend/db/repository.py](backend/db/repository.py)
`get_repo()` returns `SupabaseRepository` or `InMemoryRepository` behind one interface. Routers never know which is live. The Supabase client uses the **service key and bypasses RLS** — ownership is enforced in `deps.py`, where guards return **404 (not 403)** so resource existence isn't leaked.

### Persona seeding — two councils
Each persona `*.md` file becomes one agent. The loader ([backend/db/seed.py](backend/db/seed.py)) reads the file's **YAML frontmatter** (`name`, `role`, `weight`, `position`, `model`, `provider`, `voice_id`, `tools`, `skills`, `structural`, `conflict_partner`, `conflict_dimension`; `veto` is set when an agent declares `veto: true` or carries a `cap_rule` block) and uses the body — **with the fenced "demo-prep reference" block and HTML comments stripped** — as the `system_prompt`. The demo-prep block is the answer key and must never reach the model. There are now **two councils**: the **Judge Panel** ([personas/](personas/)`*.md`, preset `judges`) and the **VC Investment Committee** ([personas/vc/](personas/vc/)`*.md`, preset `vc`), each with role-matched `tools`/`skills`. `seed_all_councils` seeds both for the in-memory demo org; `POST /orgs/ensure-seed` seeds each missing preset on login (idempotent). `conflict_partner` is a file **stem** (e.g. `uma`) resolved to the partner's real agent_id **after** all the council's agents are created (`_seed_council`), and feeds the per-round moderator. A `veto` agent (the Skeptic) caps a clean YES to CONDITIONAL via `apply_veto_cap`. Still unwired: `cap_rule.unlock_condition` (the parser skips nested keys). **Keep `research` in every persona's `tools`** — a test asserts it, and it aliases `web_search`.

## Commands

All Python commands run from the repo root with the venv active:
```bash
source .venv/bin/activate          # Python 3.12 venv with deps preinstalled
```

| Task | Command |
|---|---|
| Run backend (no keys needed) | `uvicorn backend.main:app --reload --port 8000` |
| Health check | `curl localhost:8000/health` → `{"ok":true,...,"repo":"in-memory"}` |
| Run all tests (8, no network, mock mode) | `python -m pytest` |
| Run a single test | `python -m pytest tests/test_engine.py::test_mock_debate_produces_verdict` |
| Weave Evaluation harness | `python -m backend.evaluation` (append `1` for a one-question smoke) |
| Apply DB schema (needs `SUPABASE_DB_URL` + `psql`) | `python -m backend.db.migrate` |
| Run frontend | `cd frontend && npm install && npm run dev` |
| Frontend build / lint | `npm run build` · `npm run lint` |

Install deps freshly with `pip install -r backend/requirements.txt`. **`backend/requirements.txt` is the complete, canonical list** — the root [requirements.txt](requirements.txt) is a stale subset used only by the root `main.py` smoke test.

## Database

There are two parallel ways to apply the schema (same DDL, ROADMAP §4):
- [backend/db/migrations.sql](backend/db/migrations.sql) via `python -m backend.db.migrate` (the one wired to the app/repository).
- [supabase/migrations/](supabase/migrations/) (timestamped) via the Supabase CLI `supabase db push`.

Keep them in sync if you change the schema. **When adding a foreign key, set its `ON DELETE` rule** or deleting a parent row FK-violates: `events.agent_id` → `cascade`, `events.parent_event` / `sessions.parent_session` → `set null`; `owner_id` / `created_by` are plain `uuid` (deliberately **not** FKs to `auth.users`, so the synthetic DEMO_USER can own rows). `migrations.sql` ends with self-healing `ALTER`s that re-apply these rules on existing DBs. Auth verifies user JWTs against the project's published JWKS (ES256/RS256) — there is no shared JWT secret; verification is keyed off `SUPABASE_URL`.

## Infrastructure is managed via CLI, not dashboards

The **Vercel**, **Supabase**, and **Railway** CLIs are all installed and logged in in this terminal (Vercel `yamanbicer-8788`; Supabase project `decision-harness` / ref `cutoewanmhbkmcxdtxda` is linked; Railway authed as the project owner). **Manage their configuration yourself through these CLIs** — set env vars, link/inspect projects, trigger deploys, run migrations, read logs, etc. Do **not** tell the user to go configure something in a web dashboard/settings page; if it can be done from the CLI, do it from the CLI.

- Vercel: `vercel env`, `vercel deploy`, `vercel link`, `vercel logs`, `vercel project ls`
- Supabase: `supabase projects list`, `supabase link`, `supabase db push`, `supabase secrets set`
- Railway: `railway variables`, `railway up`, `railway logs`, `railway status`, `railway link`

## Deploy

- **Backend → Railway** via [Dockerfile](Dockerfile) + [railway.json](railway.json) (`python:3.11-slim`, installs `backend/requirements.txt`). Railway watches the **`yamanbicer/decisive` fork**, not this repo: a `PostToolUse` hook in `.claude/settings.local.json` force-pushes `HEAD:main` to `decisive` on every `git push`, which triggers the deploy. `railway up` (from a linked dir) also deploys directly.
- **Live:** frontend **https://decisiveai.vercel.app**, backend **https://decisive-production-3b01.up.railway.app** (`/health` shows live subsystem status).
- **Frontend → Vercel** (project slug `decisive`, team `yamanns`). The backend's CORS `allow_origin_regex` is pinned to both slugs to keep look-alike Vercel projects out (see `cors_origin_regex` in [backend/config.py](backend/config.py)); don't loosen it to `*.vercel.app`.

## Gotchas

- **Use `127.0.0.1`, not `localhost`**, for the API URL. macOS resolves `localhost` to IPv6 `::1` first, but uvicorn binds IPv4-only by default → `TypeError: Failed to fetch`. This is baked into `API_URL` defaults and the `.env.example` files.
- **Railway runs `startCommand` without a shell** → keep the `sh -c "... --port ${PORT:-8000}"` wrapper in [railway.json](railway.json) + the `PORT` service var, or uvicorn gets a literal `$PORT` and crash-loops the healthcheck. `weave.init()` runs in a daemon thread ([main.py](main.py)) so it can't block uvicorn from serving `/health` during the healthcheck window.
- **Supabase email confirmation is OFF** (disabled 2026-06-01 so demo signups get a session instantly and don't trip the built-in email cap of **2 emails/hr, project-wide**, which is raisable only via custom SMTP — that cap is what surfaced `email rate limit exceeded` on the signup form). Password auth is unaffected; confirmation is an independent gate. Don't try to re-toggle it from code/CLI: `supabase config` has only `push` (a whole-`config.toml` sync, no `pull` to baseline → would clobber other live auth settings), and the CLI's macOS-Keychain credential (`Supabase CLI`/`supabase`) is an OAuth **session** token, *not* a Management API PAT (`sbp_…`) — it 401s ("JWT could not be decoded") against `api.supabase.com`. Script it with a PAT (supabase.com/dashboard/account/tokens) → `PATCH /v1/projects/<ref>/config/auth {"mailer_autoconfirm":true}`, or just use the dashboard (Auth → Sign In/Providers → Email).
- **Auth smoke tests:** mint a pre-confirmed user with `POST {SUPABASE_URL}/auth/v1/admin/users` `{"email_confirm":true}` (service key), then password-grant for a real ES256 token. Admin-create **accepts `@example.com`** — it bypasses email validation (verified end-to-end); only the public `signUp` form rejects look-alike domains. `python -m backend.db.integration_smoke` runs the whole flow (login → ensure-seed → debate → IDOR) and self-cleans.
- **zsh reserves `$UID`** — never assign to `UID` in a Bash-tool script (throws "bad math expression"); use another name.
- `pytest.ini` sets `asyncio_mode = auto`, so `async def test_*` runs without an explicit marker.
- **Always push Supabase migrations after any schema change.** The two migration paths (`backend/db/migrations.sql` via `python -m backend.db.migrate` and `supabase/migrations/` via `supabase db push`) must stay in sync. After adding a column: run `supabase migration list` — any local migration without a remote timestamp must be pushed before shipping. Symptom of drift: `PGRST204: Could not find the '<column>' column` in Railway logs → `ensure-seed` crashes → `POST /sessions` returns 400 for every user. Note: `/health` returns `ok:true` even with a drifted schema — it only checks connectivity, not column existence.
- Tests force mock mode by monkeypatching `resolve_backend` to return `None` — keep new engine code routing through `resolve_backend` so it stays testable offline. The mock `agent_turn` ([agent_runner.py](backend/engine/agent_runner.py)) deliberately emits a `peer_request` sometimes so the peer-response/moderator paths exercise even keyless.
- **MCP sessions are PER-CALL, opened with nested `async with` (never `AsyncExitStack`)** ([mcp_manager.py](backend/engine/mcp_manager.py)). The debate calls tools from `asyncio.gather` child tasks; a session opened in the parent task and used from a child trips anyio's cancel-scope guard, and flattening the transport's task groups into an `AsyncExitStack` raises `unhandled errors in a TaskGroup`. Open + `initialize()` (with a timeout) + use + close all inside the calling task. The W&B MCP is **HTTP** (`https://mcp.withwandb.com/mcp`, `streamablehttp_client`), not a stdio package. `${VAR}` in `mcp_servers.json` headers/env is expanded from `os.environ` **overlaid with settings** (`WANDB_API_KEY` lives in `backend/.env`, not the exported env — a plain `os.path.expandvars` yields an empty `Bearer ` → 401).
