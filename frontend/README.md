# WS-C — Frontend (Next.js)

```bash
cd frontend
cp .env.local.example .env.local      # default API URL is http://localhost:8000
npm install
npm run dev                            # http://localhost:3000
```
Make sure the backend is running (see ../START_HERE.md). With no Supabase configured,
the backend serves the seeded **Judge Panel** org, so the page works immediately:
pick the org → Run debate → watch the mock debate stream into the Boardroom + Transcript.

## What's here (Hour 0)
- `lib/types.ts` — TS mirror of the frozen contract (keep in sync with `backend/schemas.py`)
- `lib/api.ts` — typed API client (`api.listOrgs()`, `api.createSession()`, …)
- `lib/useEventStream.ts` — SSE hook; accumulates live session events
- `lib/supabase.ts` — browser auth client (null until `NEXT_PUBLIC_SUPABASE_*` set)
- `app/page.tsx` — boardroom-lite proving the end-to-end flow

## What to build (ROADMAP §6, H1-H4)
Auth pages · Org Builder (CRUD agents/weights/voices) · full **Boardroom** (seats, streaming
bubbles, voice) · **Inspector** (per-agent thought/tool/peer tree) · **InfluenceGraph** ·
**VerdictPanel** with HITL weight sliders + "Re-run" (`api.rerun`).
