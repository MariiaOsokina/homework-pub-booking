# Ex8 — Voice pipeline

## Your answer

The voice pipeline has two modes that share a single trace-event
contract. Text mode (`run_text_mode`) reads stdin and the manager
persona replies via Llama-3.3-70B-Instruct on Nebius. Voice mode
(`run_voice_mode`) replaces only the I/O surface: Speechmatics
realtime WebSocket for STT, ElevenLabs REST for TTS. The persona
and trace shape are identical in both. This is the architectural
point — I/O is the fragile, swappable part; the brain stays stable.

TTS was switched from the starter's Rime.ai integration to
ElevenLabs. The replacement calls `POST /v1/text-to-speech/{voice_id}`
requesting raw PCM at the project's `SAMPLE_RATE`, which eliminated
the MP3-decode step and removed the `pydub`/ffmpeg dependency. The
`[voice]` extra in `pyproject.toml` and `requirements-voice.txt`
were updated to match: `speechmatics-python`, `sounddevice`, `httpx`,
`numpy` — no `pydub`.

Graceful degradation is layered. `run_voice_mode` independently
checks `SPEECHMATICS_KEY`, the `speechmatics-python` import, and
`ELEVENLABS_API_KEY`. Missing Speechmatics key → falls through to
text mode with a warning. Missing import → same fallback with an
install hint. Missing ElevenLabs key only → voice STT continues
and manager replies print rather than synthesise. Voice mode
end-to-end was not exercised on this machine (no input device
available — `sd.default.device[0] == -1`); the text-mode path runs
from the same `voice_loop.py` and validates the brain and trace
contract regardless.

Both modes emit `voice.utterance_in` and `voice.utterance_out` trace
events with payload `{text, turn, mode}`. The `mode` field
disambiguates transport for downstream analysis. Session
`sess_a2f54fba0c01` ran a four-turn text-mode conversation in
~52 seconds (22:11:01 → 22:11:52 UTC) that exercised both rule
branches. Turn 0 established a party of 6 for Friday 7:30pm —
under both caps, so accepted with a follow-up question. Turn 1
provided the contact number and a £150 deposit (under £300 cap) —
accepted with confirmation, demonstrating context continuity. Turn 2
revised the party to 12 — over the 8-person cap, so declined with
the party-size reason named and a redirect to Royal Oak. Turn 3
closed the conversation in-character.

`ManagerPersona` holds the conversation history and calls the LLM
at `temperature=0`. This produces stable rule-following rather than
strictly deterministic output — Llama-3.3-70B on Nebius doesn't
guarantee bit-exact reproducibility — but the £300/8-person caps
are applied reliably across runs.

## Citations

- `starter/voice_pipeline/voice_loop.py` — `run_voice_mode`,
  `_speak_elevenlabs`, three independent graceful-degradation branches
- `starter/voice_pipeline/manager_persona.py` — LLM-backed persona,
  rule-defined system prompt, `temperature=0`
- `pyproject.toml`, `requirements-voice.txt` — `[voice]` extra
  updated for ElevenLabs (REST + PCM path)
- `sessions/examples/ex8-voice-pipeline/sess_a2f54fba0c01/logs/trace.jsonl`
  — eight `voice.utterance_*` events across four turns, both rule
  branches exercised. Decision turns:

```jsonl
  {"event_type":"voice.utterance_out","actor":"manager","timestamp":"2026-05-24T22:11:14.715106+00:00","payload":{"text":"Aye, we can do that. I'll pencil you in for next Friday at 7:30pm. What's the contact number?","turn":0,"mode":"text"}}
  {"event_type":"voice.utterance_out","actor":"manager","timestamp":"2026-05-24T22:11:43.067047+00:00","payload":{"text":"Sorry, too many. Try The Royal Oak, they can handle bigger groups.","turn":2,"mode":"text"}}
```
