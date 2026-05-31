// Typed client for the Decision Harness API (ROADMAP §6).
import type { Agent, InfluenceGraph, Org, SessionDetail } from "./types";

export interface CreateSessionResponse { session_id: string }

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => j<{ ok: boolean; repo: string }>("/health"),
  listOrgs: () => j<Org[]>("/orgs"),
  listAgents: (orgId: string) => j<Agent[]>(`/orgs/${orgId}/agents`),
  createSession: (body: { org_id: string; question: string; context?: string; rounds?: number }) =>
    j<CreateSessionResponse>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  getSession: (id: string) => j<SessionDetail>(`/sessions/${id}`),
  rerun: (id: string, body: { weights_override?: Record<string, number>; context?: string }) =>
    j<CreateSessionResponse>(`/sessions/${id}/rerun`, { method: "POST", body: JSON.stringify(body) }),
  influence: (id: string) => j<InfluenceGraph>(`/sessions/${id}/influence`),
  streamUrl: (id: string) => `${API_URL}/sessions/${id}/stream`,
};
