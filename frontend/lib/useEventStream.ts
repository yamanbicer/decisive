"use client";
// Live session events via SSE (ROADMAP §6). Accumulates events as they arrive.
import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import type { DHEvent, EventType } from "./types";

const EVENT_NAMES: EventType[] = [
  "position", "thought", "message", "peer_request", "peer_response",
  "tool_call", "tool_result", "position_update", "orchestrator", "verdict",
  "error", "done",
];

export function useEventStream(sessionId: string | null) {
  const [events, setEvents] = useState<DHEvent[]>([]);
  const [done, setDone] = useState(false);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!sessionId) return;
    setEvents([]);
    setDone(false);
    seen.current = new Set();

    const es = new EventSource(api.streamUrl(sessionId));
    const onEvent = (e: MessageEvent) => {
      if ((e as any).type === "done") { setDone(true); es.close(); return; }
      try {
        const ev = JSON.parse(e.data) as DHEvent;
        if (ev.id && seen.current.has(ev.id)) return; // dedupe history+live overlap
        if (ev.id) seen.current.add(ev.id);
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "verdict") setDone(true);
      } catch { /* ignore non-JSON keepalives */ }
    };
    EVENT_NAMES.forEach((name) => es.addEventListener(name, onEvent as EventListener));
    es.onerror = () => es.close();
    return () => es.close();
  }, [sessionId]);

  return { events, done };
}
