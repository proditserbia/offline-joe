# Offline Joe — Milestone 4 (MS4)

> **Demo-ready, conversational, fully offline voice assistant for Raspberry Pi.**

Joe runs entirely on-device: no cloud APIs, no internet connection required.
Wake with *"Hey Joe"*, then talk naturally for up to five minutes without
repeating the wake phrase.

---

## Table of Contents

1. [Hardware Reference](#hardware-reference)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [CLI Reference](#cli-reference)
6. [Voice Skills](#voice-skills)
7. [Conversation Mode](#conversation-mode)
8. [Camera Status (MS4)](#camera-status-ms4)
9. [Storage](#storage)
10. [Logging](#logging)
11. [Diagnostics & Test Menu](#diagnostics--test-menu)
12. [Deployment (systemd)](#deployment-systemd)
13. [Troubleshooting](#troubleshooting)
14. [Development Notes](#development-notes)

---

## Hardware Reference

| Component | Detail |
|---|---|
| Platform | Raspberry Pi 5 (Pi OS 64-bit) |
| Root filesystem | `/dev/mmcblk0p2` (SD card) |
| NVMe SSD | `/mnt/ssd` — clean, available for Joe data |
| Microphone | ReSpeaker USB / USB Headset |
| Speaker | USB Audio |
| Camera | **Not present** — ribbon replaced, device confirmed absent at MS4 cut-off |
| Python | 3.10+ |

### Camera note

`camera_auto_detect=1` is set in `/boot/config.txt`.  
`rpicam-hello --list-cameras` returns *"No cameras available"*.  
`dmesg` shows no IMX708 / CSI detection.  
Both CAM/DISP ports have been tested and the ribbon reseated multiple times.  
**A replacement ribbon has been ordered.**

Joe runs in **no-camera mode** until hardware is confirmed.  Camera calls
return a graceful error — no crash, no blocking wait.

---

## Architecture

```
joe/
├── main_cli.py          CLI entry-point  (Typer)
├── main_api.py          REST API server  (FastAPI)
├── config.py            Settings loader  (env + hardware.yaml)
├── hardware.py          Typed dataclasses for all hardware config
├── router.py            Rule-based skill router
├── state.py             Thread-safe JoeState (awake flag)
├── voice/
│   ├── daemon.py        VoiceLoop — wake → listen → respond
│   ├── wakeword.py      openWakeWord detector (optional)
│   ├── stt_vosk.py      Offline speech-to-text (Vosk / Kaldi)
│   ├── tts.py           TTS (Piper preferred, espeak-ng fallback)
│   ├── vad_recorder.py  Voice activity detection (webrtcvad)
│   └── alsa_stream.py   Raw PCM capture via arecord
├── skills/
│   ├── time_date.py     Time / date skill
│   ├── system_status.py CPU / RAM / disk / SSD / temp / IP
│   ├── voice.py         Volume control
│   ├── facts.py         Remember / recall user name
│   ├── memory_skill.py  List / clear event log
│   └── mode.py          Wake / sleep mode
├── memory/
│   ├── store.py         SQLite3 event + facts store
│   ├── schema.py        DB schema
│   └── cleanup.py       TTL + overflow cleanup
├── camera/
│   └── v4l2.py          Frame capture + graceful no-camera probe
├── llm/
│   └── provider.py      OpenAI-compatible LLM fallback client
├── personality/
│   └── scaffold.py      Deterministic style wrapper
├── audio/
│   └── volume.py        Volume control (pactl / amixer)
├── diagnostics/
│   ├── deps.py          Python + binary dependency checks
│   ├── audio.py         ALSA device probes
│   └── storage.py       Disk / SSD usage probes
└── utils/
    ├── logging.py       Enterprise rotating-file + console logging
    └── shell.py         Subprocess wrapper
```

**Signal flow:**

```
arecord (ALSA) → AlsaPCMStream
                      │
              ┌───────┴────────┐
           WakewordDetector  VadRecorder
           (openWakeWord /    (webrtcvad)
            STT fallback)         │
                 │           VoskSTT
                 │                │
                 └────────────────┘
                          │
                       Router
                    ┌────┴────┐
                  Skill    LLM fallback
                          (optional)
                          │
                    Personality.wrap()
                          │
                       Speaker
                    (Piper / espeak-ng → aplay)
```

---

## Quick Start

### 1. Clone and install core dependencies

```bash
git clone https://github.com/proditserbia/offline-joe
cd offline-joe
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Install MS4 voice dependencies

```bash
pip install -r requirements_m4.txt
```

> `requirements_m4.txt` is the single unified file for all MS4 dependencies
> (core + voice + optional wakeword engine).

### 3. Download a Vosk model

```bash
mkdir -p /mnt/ssd/models
cd /mnt/ssd/models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
cd ..
```

The default `config/hardware.yaml` expects the model at
`models/vosk-model-small-en-us-0.15` relative to the project root.

### 4. Download a Piper TTS model

```bash
mkdir -p /mnt/ssd/models/piper
cd /mnt/ssd/models/piper
# Example: en_US-joe-medium
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx.json
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/MODEL_CARD
```

Set `piper.model_path: models/piper/en_US-amy-medium.onnx` in `hardware.yaml`.

### 5. Configure hardware

Edit `config/hardware.yaml` — at minimum, set:

```yaml
audio:
  input_device: "plughw:CARD=YourMic,DEV=0"
  output_device: "plughw:CARD=YourSpeaker,DEV=0"
```

Run `aplay -l` and `arecord -l` to list available devices.

### 6. Run the voice demo

```bash
joe run-voice
```

Say **"Hey Joe"** — Joe replies **"Hi."** and listens for ~2–5 minutes.

### 7. Verify status

```bash
joe status
```

---

## Configuration

All hardware settings live in `config/hardware.yaml`.  Override the path with:

```bash
export JOE_HARDWARE_YAML=/path/to/your/hardware.yaml
```

Other environment variables:

| Variable | Default | Description |
|---|---|---|
| `JOE_DATA_DIR` | `~/.offlinejoe` | Data directory (DB, logs, camera frames) |
| `JOE_DB_PATH` | `$JOE_DATA_DIR/memory.sqlite3` | SQLite database |
| `JOE_HARDWARE_YAML` | `config/hardware.yaml` | Hardware config path |
| `JOE_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, …) |
| `JOE_LOG_DIR` | *(none)* | Directory for rotating log file |

### Key `hardware.yaml` sections

#### `conversation`

```yaml
conversation:
  active_listen_min_s: 120   # min seconds in conversation mode after wake
  active_listen_max_s: 300   # max seconds
  wake_phrase: "Hey Joe"
  wake_ack: "Hi."
```

#### `camera` (MS4 — no camera present)

```yaml
camera:
  enabled: false             # Set true once hardware confirmed
  device: "/dev/video0"
  backend: "v4l2"
```

#### `storage`

```yaml
storage:
  ssd_mount: "/mnt/ssd"       # NVMe SSD for large data
  root_device: "/dev/mmcblk0p2"  # SD card root
```

#### `llm`

```yaml
llm:
  enabled: false              # true to enable LLM fallback
  base_url: "http://localhost:11434/v1"   # Ollama or any OpenAI-compat server
  model: "llama3"
  timeout_s: 20
```

---

## CLI Reference

```
joe --help
```

| Command | Description |
|---|---|
| `joe status` | Show system info, volume, camera state, storage |
| `joe ask "<text>"` | Route text through skills (no audio) |
| `joe run-voice` | Start the MS4 voice loop |
| `joe camera-test` | Capture a single frame (or report gracefully if absent) |
| `joe memory list` | Show recent conversation events |
| `joe memory facts` | Show saved facts (e.g. user name) |
| `joe memory clear` | Clear events and/or facts |
| `joe memory cleanup` | TTL + overflow cleanup |
| `joe volume get` | Current volume |
| `joe volume set <0-100>` | Set volume |
| `joe volume mute [true/false]` | Mute / unmute |
| `joe mode sleep` | Put Joe to sleep |
| `joe mode wake` | Wake Joe |

---

## Voice Skills

| Trigger phrase | Skill | Example response |
|---|---|---|
| *"time"*, *"what time is it"* | `time_date` | "It's 10:08 PM on Friday, March 1st." |
| *"status"*, *"cpu"*, *"ram"* | `system_status` | "pi5. CPU load is 0.12. Memory is 34 percent…" |
| *"volume up"*, *"mute"* | `voice` | Volume adjusted |
| *"my name is Alice"* | `facts` | "Got it — I'll remember that." |
| *"what's my name"* | `facts` | "Your name is Alice." |
| *"go to sleep"* | `mode` | Joe stops listening |
| *"wake up"* | `mode` | Joe starts listening |
| *"clear memory"* | `memory` | Events cleared |
| Anything else | LLM fallback (if enabled) | Short answer from local model |

---

## Conversation Mode

After the wake phrase is detected, Joe enters **active listening mode**:

- No repeated *"Hey Joe"* required for up to 5 minutes.
- Natural back-and-forth dialogue.
- Local skills are tried first; unmatched queries go to the LLM fallback
  (if enabled), or Joe politely says what it can help with.
- Say *"stop"* or *"cancel"* to exit conversation mode early.
- The active window duration is randomised between
  `conversation.active_listen_min_s` and `conversation.active_listen_max_s`.

### Wake detection modes

1. **openWakeWord** (preferred): Low-latency, always listening.
   Requires `openwakeword` and `onnxruntime` packages.
   The bundled `wakeword/hey_joe.tflite` is used automatically.

2. **STT-based fallback**: Joe records utterances via VAD and checks whether
   the wake phrase appears in the transcript.  Higher latency but zero
   additional dependencies.

---

## Camera Status (MS4)

| Check | Result |
|---|---|
| `camera_auto_detect=1` in `/boot/config.txt` | ✓ set |
| `rpicam-hello --list-cameras` | No cameras available |
| `dmesg` IMX708 / CSI detection | Not detected |
| `/dev/video*` device node | Absent |
| CAM/DISP ports tested | Both tested |
| Ribbon reseated | Multiple times |
| Replacement ribbon | **Ordered** |

**Joe's response:** `camera.enabled: false` in `hardware.yaml`.
All camera calls return a clear, non-crashing `CameraStatus(ok=False, …)`.
No frame capture is attempted.  The `joe camera-test` command prints a
human-readable note and exits with code 1.

To re-enable once hardware is confirmed:

```yaml
# config/hardware.yaml
camera:
  enabled: true
  device: "/dev/video0"
```

---

## Storage

MS4 hardware layout:

| Mount | Device | Purpose |
|---|---|---|
| `/` | `/dev/mmcblk0p2` | Root filesystem (SD card) |
| `/mnt/ssd` | NVMe SSD | Joe data: models, DB, camera frames, logs |

Move Joe's data directory to the SSD:

```bash
export JOE_DATA_DIR=/mnt/ssd/offlinejoe
export JOE_LOG_DIR=/mnt/ssd/offlinejoe/logs
joe run-voice
```

The SSD usage is reported by `joe status` and the `system_status` voice skill.

---

## Logging

Joe uses Python's standard `logging` module with two handlers:

| Handler | Format | Level |
|---|---|---|
| Console (stderr) | `timestamp \| LEVEL \| logger \| message` | INFO (DEBUG when `JOE_LOG_LEVEL=DEBUG`) |
| Rotating file | Full format including thread, file, line | DEBUG (all records) |

File log: 10 MB per file, 5 backups.

Enable file logging:

```bash
export JOE_LOG_DIR=/mnt/ssd/offlinejoe/logs
joe run-voice
```

Enable debug output:

```bash
export JOE_LOG_LEVEL=DEBUG
joe run-voice
```

---

## Diagnostics & Test Menu

```bash
python joe_test_menu.py
```

Menu options:

| Option | What it checks |
|---|---|
| 1) System status | Config paths, audio, camera, storage |
| 2) Dependency check | Python packages + system binaries |
| 3) Audio probe | ALSA backend, volume, arecord/aplay |
| 4) Storage probe | Root + SSD mount sizes |
| 5) Camera test | Probe + frame capture (graceful if absent) |
| 6) Run voice loop | Full MS4 conversation loop |

---

## Deployment (systemd)

```bash
sudo cp deploy/joe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable joe
sudo systemctl start joe
sudo journalctl -u joe -f
```

The service file runs `joe run-voice` as the `pi` user.

---

## Troubleshooting

### `VAD not available`

```bash
pip install webrtcvad
# or
pip install -r requirements_m4.txt
```

### `STT not available — set vosk.model_path`

Download a Vosk model (see Quick Start step 3) and set
`vosk.model_path` in `hardware.yaml`.

### Audio device errors

```bash
aplay -l        # list playback devices
arecord -l      # list capture devices
```

Set `audio.input_device` / `audio.output_device` in `hardware.yaml` to a
device from these lists.

### Camera absent

See [Camera Status (MS4)](#camera-status-ms4).  Set `camera.enabled: false`
in `hardware.yaml` and operate without camera until hardware is confirmed.

### SSD not mounted

```bash
lsblk
sudo mount /dev/nvme0n1p1 /mnt/ssd
```

Add the mount to `/etc/fstab` for persistence.

### `hardware.yaml not found`

```bash
export JOE_HARDWARE_YAML=/absolute/path/to/config/hardware.yaml
```

---

## Development Notes

- **No cloud deps** — all inference runs locally.
- **LLM fallback** is opt-in (`llm.enabled: false` by default).  Designed for
  a local Ollama server or any OpenAI-compatible endpoint.
- **Personality** is fully deterministic: `personality.warmth/humor/directness`
  control style via simple rules — no randomness, no LLM.
- **Memory** (SQLite3) stores conversation events and facts.  Auto-cleanup
  via TTL and overflow limits.
- **API server** (`joe.main_api`): start with
  `uvicorn joe.main_api:app --port 8080` for programmatic access.

### Running tests / lint

```bash
pip install -e ".[dev]"   # if dev extras are defined
python -m py_compile $(find joe -name '*.py')   # basic syntax check
```
