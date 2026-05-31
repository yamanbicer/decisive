-- Decision Harness — Supabase schema (ROADMAP §4)
-- Run in the Supabase SQL editor (or `supabase db push`). Idempotent-ish: safe to re-run after a reset.

create extension if not exists pgcrypto;   -- gen_random_uuid()

-- Users come from Supabase Auth (auth.users). We reference auth.uid().

create table if not exists orgs (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid references auth.users(id),
  name        text not null,
  description text,
  preset      text,                       -- 'vc' | 'board' | 'judges' | null
  created_at  timestamptz default now()
);

create table if not exists agents (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references orgs(id) on delete cascade,
  name          text not null,            -- "Ra'ad Siraj"
  role          text not null,            -- "Head of AI Governance"
  system_prompt text not null,
  model         text not null default 'claude-sonnet-4-6',
  provider      text not null default 'anthropic',   -- 'anthropic' | 'wandb'
  weight        numeric not null default 1.0,
  voice_id      text,                     -- ElevenLabs voice id
  tools         jsonb default '[]',       -- ["research","company_data","wandb"]
  position      int default 0,            -- seat order in the boardroom
  created_at    timestamptz default now()
);

create table if not exists sessions (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references orgs(id) on delete cascade,
  created_by       uuid references auth.users(id),
  question         text not null,
  context          text,
  weights_override jsonb,                 -- {agent_id: weight} for HITL re-run
  status           text not null default 'pending',  -- pending|running|done|error
  rounds           int default 3,
  final_verdict    jsonb,
  weave_trace_url  text,
  parent_session   uuid references sessions(id),     -- re-runs / comparison
  created_at       timestamptz default now()
);

-- The inspectable transcript. Append-only, ordered by seq.
create table if not exists events (
  id            uuid primary key default gen_random_uuid(),
  session_id    uuid not null references sessions(id) on delete cascade,
  seq           bigint generated always as identity,
  round         int not null,
  agent_id      uuid references agents(id),
  type          text not null,
  content       jsonb not null,
  parent_event  uuid references events(id),
  influenced_by jsonb default '[]',
  created_at    timestamptz default now()
);
create index if not exists events_session_seq_idx on events(session_id, seq);

-- Denormalized per-round stance for charts + influence graph.
create table if not exists positions (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references sessions(id) on delete cascade,
  round       int not null,
  agent_id    uuid not null references agents(id) on delete cascade,
  stance      text not null,              -- 'YES' | 'NO' | 'CONDITIONAL'
  score       numeric not null,           -- 0..10
  confidence  numeric not null,           -- 0..1
  rationale   text,
  unique (session_id, round, agent_id)
);

-- ─── RLS ───────────────────────────────────────────────────────────────────
-- Hackathon-pragmatic: enable RLS, allow any authenticated user to read/write.
-- Tighten to `owner_id = auth.uid()` post-event. The service-key backend bypasses RLS.
alter table orgs      enable row level security;
alter table agents    enable row level security;
alter table sessions  enable row level security;
alter table events    enable row level security;
alter table positions enable row level security;

do $$
declare t text;
begin
  foreach t in array array['orgs','agents','sessions','events','positions'] loop
    execute format('drop policy if exists authed_all on %I;', t);
    execute format(
      'create policy authed_all on %I for all to authenticated using (true) with check (true);', t);
  end loop;
end $$;
