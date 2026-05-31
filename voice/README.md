# WS-D — Voice / Virtual Meeting

Real-time ElevenLabs **speech-to-speech**, driven by the Claude orchestrator (NOT ElevenLabs Agents). See ROADMAP §10.

## Tiers (the boardroom page is the same artifact in all of them)
1. **Tier 1 — Web-boardroom voices (PRIMARY):** the frontend boardroom subscribes to the session `events` SSE stream; each `message` event → that agent's ElevenLabs streaming-TTS WebSocket (distinct `voice_id`) → spoken in-browser. Human mic → ElevenLabs realtime STT → POST back into the session as context.
2. **Tier 2 — Into Zoom/Meet (stretch):** point a **Recall.ai Output Media** bot at the boardroom page's public URL. Same page, now in the call.
3. **Tier 0 — Fallback:** screen-share the boardroom browser tab into Zoom with tab-audio on (one-way, zero code).

## APIs
- Per-voice speech: `wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input` (Flash v2.5)
- Human → agents: `wss://api.elevenlabs.io/v1/speech-to-text/realtime`
- Browser auth: backend issues a short-lived token via `/voice/token` (don't ship the raw key client-side)

## Hour-0 check
```bash
pip install -r voice/requirements.txt
export ELEVENLABS_API_KEY=...
python voice/hello_tts.py   # writes voice/out/*.mp3 in 3 distinct voices
```
Needs an ElevenLabs **Creator/Pro** plan for 3-5 concurrent voices.

## Where to plug in
You consume `GET /sessions/{id}/stream` (SSE) — same as the frontend. Each `message` event has `content.text` and `agent_id`; look up the agent's `voice_id` from `GET /orgs/{org_id}/agents`.
