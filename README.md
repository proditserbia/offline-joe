# Offline Joe — Milestone 4 (Demo-ready conversational Joe)

This build adds the **MS4 voice demo loop**:

- Wake phrase: **"Hey Joe"**
- Immediate spoken acknowledgement: **"Hi."**
- After wake, Joe remains in **conversation mode** for ~2–5 minutes
- No repeated wakeword required (natural back-and-forth)
- **Local skills first**, then **LLM fallback** (single provider, no tools, no autonomy)
- **Rule-based personality scaffold** (deterministic)
- **Camera hooks** (init + basic frame capture; no recognition yet)

---

## What's new vs M3 (summary)

### Conversation mode
- Added a `joe run-voice` command that runs the wake→listen→respond loop.
- Once wake triggers, Joe stays active for `conversation.active_listen_min_s ... max_s`.

### LLM fallback (lightweight)
- Optional, disabled by default in `config/hardware.yaml`.
- Uses a single OpenAI-compatible chat endpoint (`llm.base_url`).
- No tools, no long-term memory, short responses.

### Personality scaffolding
- Deterministic style wrapper (`personality.warmth / humor / directness`).

### Camera/perception hooks
- `joe camera-test` captures a single frame from `camera.device` (default `/dev/video0`).
- Voice loop also performs a non-blocking init capture on startup.

---

## Quick start

### 1) Install base deps

```bash
pip install -e .
```

### 2) Install optional voice deps

```bash
pip install -r requirements_voice.txt
```

### 3) Configure hardware

Edit `config/hardware.yaml`:
- `vosk.model_path` (required)
- `piper.model_path` (optional, but recommended)
- `audio.input_device` / `audio.output_device`
- `camera.device` = `/dev/video0`

### 4) Run the voice demo

```bash
joe run-voice
```

### 5) Camera sanity test

```bash
joe camera-test
```

---

## Notes

- Wakeword model is bundled at `wakeword/hey_joe.tflite` and used automatically if `wakeword.model_path` is null.
- LLM fallback defaults to an Ollama-style OpenAI-compatible endpoint (`http://localhost:11434/v1`).
  You can change this to any OpenAI-compatible server.
