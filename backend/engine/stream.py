"""In-process pub/sub for live session events (ROADMAP §6 streaming).

The debate engine `publish()`es each event; the `/sessions/{id}/stream` SSE
endpoint and the voice bridge `subscribe()` to receive them in real time.
For multi-process deploys swap this for Supabase Realtime on the `events` table.
"""
import asyncio
from collections import defaultdict

_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


def subscribe(session_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[session_id].append(q)
    return q


def unsubscribe(session_id: str, q: asyncio.Queue) -> None:
    if q in _subscribers.get(session_id, []):
        _subscribers[session_id].remove(q)


def publish(session_id: str, event: dict) -> None:
    for q in list(_subscribers.get(session_id, [])):
        q.put_nowait(event)


def close(session_id: str) -> None:
    """Signal end-of-stream to all subscribers (sentinel None)."""
    for q in list(_subscribers.get(session_id, [])):
        q.put_nowait(None)
