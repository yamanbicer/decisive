"""WS-D Hour-0 proof: make ElevenLabs speak a line in N distinct voices.

This validates your ELEVENLABS_API_KEY + voice ids before wiring the real-time
boardroom. The CANONICAL voice path is in the browser (frontend) via the
streaming-TTS WebSocket; this Python script is just a quick local check.

    pip install -r voice/requirements.txt
    export ELEVENLABS_API_KEY=...
    python voice/hello_tts.py

Real-time path (ROADMAP §10): browser → wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input
Human → agents: wss://api.elevenlabs.io/v1/speech-to-text/realtime
"""
import os

# A few stock ElevenLabs voice ids (swap for ones you pick per board member).
VOICES = {
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
    "Antoni": "ErXwobaYiN019PkySvjV",
}

LINE = "I've reviewed the proposal. On balance, I lean conditional — strong instrumentation, unclear ownership."


def main() -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("Set ELEVENLABS_API_KEY (https://elevenlabs.io > Profile).")

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=api_key)
    os.makedirs("voice/out", exist_ok=True)
    for name, voice_id in VOICES.items():
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_flash_v2_5",   # ~75ms, lowest latency
            text=f"This is {name}. {LINE}",
            output_format="mp3_44100_128",
        )
        path = f"voice/out/{name}.mp3"
        with open(path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        print(f"✓ wrote {path}")
    print("Open the files in voice/out/ — each should be a distinct voice.")


if __name__ == "__main__":
    main()
