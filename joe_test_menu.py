#!/usr/bin/env python3

import os
os.environ["VOSK_LOG_LEVEL"] = "0"
import sys
sys.path.insert(0, "/opt/offlinejoe/")
import json
import wave
import time
import subprocess
import pyaudio
import yaml
from contextlib import redirect_stderr
import warnings
# ...pre ostalih import-a
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="webrtcvad"
)
os.environ["ORT_LOG_SEVERITY_LEVEL"] = "3"
# os.environ["VOSK_LOG_LEVEL"] = "0"

HARDWARE_CONFIG_PATH = "/opt/offlinejoe/config/hardware.yaml"

# Pokušaj da učitaš dodatne pakete za M2 stvari
try:
    import numpy as np
except ImportError:
    np = None

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

try:
    from vosk import Model, KaldiRecognizer
except ImportError:
    Model = None
    KaldiRecognizer = None

try:
    from openwakeword.model import Model as WakeModel
except ImportError:
    WakeModel = None


# ------------------------------
# Config loading
# ------------------------------
def load_config():
    if not os.path.exists(HARDWARE_CONFIG_PATH):
        print(f"❌ Config file not found: {HARDWARE_CONFIG_PATH}")
        sys.exit(1)

    with open(HARDWARE_CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)

    try:
        vosk_model_path = cfg["vosk"]["model_path"]
        piper_model_path = cfg["piper"]["model_path"]
        audio_cfg = cfg["audio"]
    except KeyError as e:
        print(f"❌ Missing key in hardware.yaml: {e}")
        sys.exit(1)

    wake_cfg = cfg.get("wakeword", {})
    vad_cfg = cfg.get("vad", {})
    stt_cfg = cfg.get("stt", {})


    return {
        "vosk_model_path": vosk_model_path,
        "piper_model_path": piper_model_path,
        "audio_output_device": audio_cfg.get("output_device", "default"),
        "input_rate": int(audio_cfg.get("input_rate", 16000)),
        "input_channels": int(audio_cfg.get("input_channels", 1)),
        "input_device_index": audio_cfg.get("input_device_index", None),
        "record_seconds": int(audio_cfg.get("record_seconds", 3)),

        "wakeword_model_path": wake_cfg.get("model_path"),
        "wakeword_threshold": float(wake_cfg.get("threshold", 0.5)),
        "wakeword_frame_ms": int(wake_cfg.get("frame_ms", 80)),
        "wakeword_min_activation_frames": int(
            wake_cfg.get("min_activation_frames", 3)
        ),

        "vad_aggressiveness": int(vad_cfg.get("aggressiveness", 2)),
        "vad_silence_ms": int(vad_cfg.get("silence_ms", 800)),
        "vad_max_record_ms": int(vad_cfg.get("max_record_ms", 8000)),
        "stt_mode": str(stt_cfg.get("mode", "auto")).lower(),
        "stt_grammar": list(stt_cfg.get("grammar", [])) or [],
    }

CONFIG = load_config()

# ------------------------------
# M3 init (Memory + Router)
# ------------------------------
try:
    from joe.config import load_settings
    from joe.memory.store import MemoryStore
    from joe.state import JoeState
    from joe.skills.registry import SkillRegistry
    from joe.router import Router
    from joe.skills.base import SkillContext
except ImportError:
    load_settings = None

_M3 = None

def get_m3():
    global _M3
    if _M3 is not None:
        return _M3

    if load_settings is None:
        print("⚠️ M3 modules not available (joe package not installed).")
        _M3 = None
        return None

    settings = load_settings()
    memory = MemoryStore(str(settings.db_path))
    memory.init()
    state = JoeState()
    registry = SkillRegistry.build_default()
    router = Router(registry)

    _M3 = (settings, memory, state, router)
    return _M3

def _fmt_uptime_hm(uptime_s: int) -> str:
    h = uptime_s // 3600
    m = (uptime_s % 3600) // 60
    return f"{h}h{m:02d}m"

def _format_result_for_console(res) -> str:
    data = getattr(res, "data", None) or {}

    # Pretty-print known payload: system_status
    if "host" in data and "load1" in data and "ram_percent" in data and "disk_percent" in data:
        host = data.get("host", "unknown")
        load1 = float(data.get("load1", 0.0))
        ram = float(data.get("ram_percent", 0.0))
        disk = float(data.get("disk_percent", 0.0))
        uptime_s = int(data.get("uptime_s", 0))
        temp = data.get("temp_c", None)
        ip = data.get("ip", None)

        msg = (
            f"{host}: CPU load {load1:.2f}, RAM {ram:.0f}%, disk {disk:.0f}%, "
            f"uptime {_fmt_uptime_hm(uptime_s)}"
        )
        if temp is not None:
            try:
                msg += f", temp {float(temp):.1f}°C"
            except Exception:
                pass
        if ip:
            msg += f", IP {ip}"
        return msg

    # Default fallback: show text
    return getattr(res, "text", str(res))


def route_and_speak(user_text: str, source: str = "voice"):
    m3 = get_m3()
    if m3 is None:
        tts("You said " + user_text if user_text.strip() else "I could not understand you.")
        return

    _, memory, state, router = m3
    ctx = SkillContext(source=source, state=state, memory=memory)
    res = router.handle_text(user_text, ctx)

    # Console: numeric/debug-friendly
    try:
        print("🧾 Result:", _format_result_for_console(res))
    except Exception:
        pass

    # TTS: spoken-friendly
    tts(res.text)

# ------------------------------
# STT (Vosk) – lazy load
# ------------------------------
_VOSK_MODEL = None


def get_vosk_model():
    global _VOSK_MODEL

    if Model is None or KaldiRecognizer is None:
        print("❌ Vosk is not installed (vosk package missing).")
        return None

    if _VOSK_MODEL is None:
        model_path = CONFIG["vosk_model_path"]
        if not os.path.isdir(model_path):
            print(f"❌ Vosk model not found at: {model_path}")
            return None
        print("📦 Loading Vosk model...")
        _VOSK_MODEL = Model(model_path)
        print("✔️ Vosk model loaded.")

    return _OSK_MODEL if False else _VOSK_MODEL  # small hack to keep linter quiet


def stt(filename="mic.wav", mode=None):
    model = get_vosk_model()
    if model is None:
        return ""

    rate = CONFIG["input_rate"]
    mode = (mode or CONFIG.get("stt_mode", "auto")).lower().strip()

    # Decide recognizer mode
    use_grammar = False
    if mode == "command":
        use_grammar = True
    elif mode == "free":
        use_grammar = False
    elif mode == "auto":
        # auto: try grammar first, fallback handled outside (Option 6)
        use_grammar = True
    else:
        use_grammar = False

    if use_grammar and CONFIG.get("stt_grammar"):
        rec = KaldiRecognizer(model, rate, json.dumps(CONFIG["stt_grammar"]))
    else:
        rec = KaldiRecognizer(model, rate)

    wf = wave.open(filename, "rb")
    if wf.getframerate() != rate:
        print(f"⚠️ Warning: WAV rate is {wf.getframerate()} Hz, expected {rate} Hz.")

    print("🧠 Running STT...")
    while True:
        data = wf.readframes(4000)
        if not data:
            break
        rec.AcceptWaveform(data)

    result = json.loads(rec.FinalResult())
    text = (result.get("text", "") or "").strip()
    print("🗣️ Recognized:", text if text else "<no speech detected>")
    return text

# ------------------------------
# TTS (Piper)
# ------------------------------
def tts(text):
    if not text:
        print("⚠️ Empty text, nothing to speak.")
        return

    piper_model = CONFIG["piper_model_path"]
    audio_device = CONFIG["audio_output_device"]

    if not os.path.isfile(piper_model):
        print(f"❌ Piper model not found at: {piper_model}")
        return

    print("🔊 Speaking:", text)

    piper_cmd = [
        "piper",
        "--model",
        piper_model,
        "--output-raw",
        "--text",
        text,
    ]

    # Piper default: 22050 Hz, 16-bit, mono
    aplay_cmd = [
        "aplay",
        "-D",
        audio_device,
        "-f",
        "S16_LE",
        "-c",
        "1",
        "-r",
        "22050",
    ]

    try:
        p1 = subprocess.Popen(piper_cmd, stdout=subprocess.PIPE)
        p2 = subprocess.Popen(aplay_cmd, stdin=p1.stdout)
        p1.stdout.close()
        p2.communicate()
    except FileNotFoundError as e:
        print("❌ Error running piper/aplay:", e)
    except Exception as e:
        print("❌ TTS error:", e)


# ------------------------------
# Plain recording (fixed duration)
# ------------------------------
def record_audio(filename="mic.wav", duration=None):
    duration = duration or CONFIG["record_seconds"]
    rate = CONFIG["input_rate"]
    channels = CONFIG["input_channels"]
    device_index = CONFIG["input_device_index"]

    print(f"🎤 Recording {duration} seconds at {rate} Hz...")

    pa = pyaudio.PyAudio()
    try:
        # Privremeno utišaj ALSA/Jack spam na stderr dok otvaraš stream
        with open(os.devnull, "w") as devnull, redirect_stderr(devnull):
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024,
            )
    except Exception as e:
        print("❌ Could not open input device:", e)
        pa.terminate()
        return False

    frames = []
    total_frames = int(rate / 1024 * duration)

    for _ in range(total_frames):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    pa.terminate()

    wf = wave.open(filename, "wb")
    wf.setnchannels(channels)
    wf.setsampwidth(2)
    wf.setframerate(rate)
    wf.writeframes(b"".join(frames))
    wf.close()

    print("✔️ Audio saved as", filename)
    return True


# ------------------------------
# WebRTC VAD recording (until silence)
# ------------------------------
def record_until_silence(filename="utterance.wav"):
    if webrtcvad is None or np is None:
        print("❌ webrtcvad or numpy not installed – cannot do VAD-based recording.")
        return False

    rate = CONFIG["input_rate"]
    channels = CONFIG["input_channels"]
    device_index = CONFIG["input_device_index"]

    frame_ms = 20              # 20 ms frame za WebRTC VAD
    frame_bytes = int(rate * frame_ms / 1000) * 2  # 16-bit PCM -> *2
    vad = webrtcvad.Vad(CONFIG["vad_aggressiveness"])

    silence_ms = CONFIG["vad_silence_ms"]
    max_record_ms = CONFIG["vad_max_record_ms"]

    max_frames = max_record_ms // frame_ms
    silence_frames_limit = silence_ms // frame_ms

    print(
        f"🎤 Recording with VAD (frame={frame_ms}ms, "
        f"silence={silence_ms}ms, max={max_record_ms}ms)..."
    )

    pa = pyaudio.PyAudio()
    try:
        with open(os.devnull, "w") as devnull, redirect_stderr(devnull):
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=int(rate * frame_ms / 1000),
            )
    except Exception as e:
        print("❌ Could not open input device:", e)
        pa.terminate()
        return False


    frames = []
    num_silent = 0
    num_voiced_total = 0
    started = False

    try:
        for i in range(max_frames):
            data = stream.read(
                int(rate * frame_ms / 1000),
                exception_on_overflow=False
            )

            if len(data) != frame_bytes:
                # Nešto nije u redu, ali pokušajmo da nastavimo
                pass

            is_speech = vad.is_speech(data, rate)

            if is_speech:
                frames.append(data)
                num_voiced_total += 1
                num_silent = 0
                if not started:
                    started = True
                    print("🎙️ Speech detected, start of utterance...")
            else:
                if started:
                    num_silent += 1
                    frames.append(data)
                else:
                    # Još uvek čekamo prvi govor – ignoriši početnu tišinu
                    continue

            if started and num_silent >= silence_frames_limit:
                print("🤫 Silence detected, end of utterance.")
                break
        else:
            print("⏱️ Max record duration reached.")
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames or not started:
        print("⚠️ No speech captured.")
        return False

    wf = wave.open(filename, "wb")
    wf.setnchannels(channels)
    wf.setsampwidth(2)
    wf.setframerate(rate)
    wf.writeframes(b"".join(frames))
    wf.close()

    print("✔️ Utterance saved as", filename)
    return True


# ------------------------------
# Wakeword (openWakeWord) – lazy load
# ------------------------------
_WAKE_MODEL = None

def get_wake_model():
    global _WAKE_MODEL

    if WakeModel is None or np is None:
        print("❌ openWakeWord ili numpy nisu instalirani.")
        return None

    if _WAKE_MODEL is None:
        print("📦 Loading built-in openWakeWord models...")
        # Koristimo podrazumevane modele iz paketa, bez dodatnih argumenata
        _WAKE_MODEL = WakeModel()
        print("✔️ Wakeword model(s) loaded.")

    return _WAKE_MODEL


def wait_for_wakeword(timeout_seconds=60):
    """
    Čita audio frejmovima (80 ms) i koristi openWakeWord da sačeka aktivaciju.
    Vraća True ako je wakeword detektovan u roku, False u suprotnom.
    """
    if np is None:
        print("❌ numpy not installed – cannot run wakeword detection.")
        return False

    model = get_wake_model()
    if model is None:
        return False

    rate = CONFIG["input_rate"]
    channels = CONFIG["input_channels"]
    device_index = CONFIG["input_device_index"]

    frame_ms = CONFIG["wakeword_frame_ms"]
    frame_samples = int(rate * frame_ms / 1000)

    threshold = CONFIG["wakeword_threshold"]
    min_frames = CONFIG["wakeword_min_activation_frames"]

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=frame_samples,
        )
    except Exception as e:
        print("❌ Could not open input device:", e)
        pa.terminate()
        return False

    print(
        f"\n👂 Listening for wakeword (frame={frame_ms}ms, "
        f"threshold={threshold}, min_frames={min_frames})..."
    )
    print("   Say the wake phrase, or press Ctrl+C to abort.\n")

    start_time = time.time()
    consecutive_hits = 0

    try:
        while True:
            if time.time() - start_time > timeout_seconds:
                print("⏱️ Wakeword timeout reached.")
                return False

            data = stream.read(frame_samples, exception_on_overflow=False)
            # Pretvori u int16 numpy array
            audio_frame = np.frombuffer(data, dtype=np.int16)

            # 1) RMS gate – ignoriši vrlo tihi šum
            rms = float(np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2)))
            min_rms = float(CONFIG.get("wakeword_min_rms", CONFIG.get("wakeword", {}).get("min_rms", 700.0)))
            if rms < min_rms:
                 # pretiho, verovatno šum → preskoči ovaj frejm
                 continue

            # 2) openWakeWord predikcija
            prediction = model.predict(audio_frame)

            if isinstance(prediction, dict) and prediction:
                 # npr. {"hey_jarvis": 0.12, "alexa": 0.03, ...}
                 name, score = max(prediction.items(), key=lambda kv: kv[1])
            elif isinstance(prediction, list) and prediction and isinstance(prediction[0], dict):
                 # lista dict-ova, uzmi max od svih
                 best = []
                 for p in prediction:
                      if p:
                           best.append(max(p.items(), key=lambda kv: kv[1]))
                 if best:
                      name, score = max(best, key=lambda kv: kv[1])
                 else:
                      name, score = "unknown", 0.0
            else:
                 try:
                      score = float(prediction)
                      name = "scalar"
                 except Exception:
                      score = 0.0
                      name = "unknown"

            if score > 0.1:
                 print(f"   debug wake='{name}' score={score:.3f} rms={rms:.1f}")


            if score >= threshold:
                consecutive_hits += 1
                if consecutive_hits == 1:
                    print(f"   Wakeword score={score:.3f} (1/{min_frames})")
                else:
                    print(
                        f"   Wakeword score={score:.3f} "
                        f"({consecutive_hits}/{min_frames})"
                    )

                if consecutive_hits >= min_frames:
                    print("✅ Wakeword detected!")
                    return True
            else:
                consecutive_hits = 0

    except KeyboardInterrupt:
        print("\n⏹️ Wakeword listening interrupted by user.")
        return False
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

# ------------------------------
# Play beep after wakeword
# ------------------------------

def play_beep(duration_ms=180, freq=880, rate=22050):
    """Short acknowledgement beep so the user knows when Joe starts listening."""
    import math
    import struct

    audio_device = CONFIG["audio_output_device"]
    n_samples = int(rate * (duration_ms / 1000.0))
    amp = 0.20
    buf = bytearray()

    for i in range(n_samples):
        s = amp * math.sin(2 * math.pi * freq * (i / rate))
        buf += struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))

    aplay_cmd = ["aplay", "-D", audio_device, "-f", "S16_LE", "-c", "1", "-r", str(rate)]

    try:
        p = subprocess.Popen(aplay_cmd, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.stdin.write(buf)
        p.stdin.close()
        p.wait(timeout=2)
    except Exception as e:
        print("⚠️ Beep failed:", e)

# ------------------------------
# Test functions (menu commands)
# ------------------------------
def safe_tts(text: str):
    try:
        tts(text)
    except BrokenPipeError:
        print("⚠️ BrokenPipeError ignored (audio device issue).")
    except Exception as e:
        print("⚠️ TTS failed:", e)

def test_tts_only():
    print("\n=== TTS Test ===")
    sample_text = "Hello, this is Offline Joe speaking from the Raspberry Pi."
    tts(sample_text)
    print("✅ TTS test finished.\n")


def test_stt_only():
    print("\n=== STT Test ===")
    if not record_audio("stt_test.wav"):
        return
    text = stt("stt_test.wav")
    print("✅ STT test finished.\n")
    return text


def test_roundtrip():
    print("\n=== Roundtrip Test (Record → STT → TTS) ===")
    if not record_audio("roundtrip.wav"):
        return
    text = stt("roundtrip.wav")
    route_and_speak(text, source="voice")

    print("✅ Roundtrip test finished.\n")


def test_wakeword_roundtrip():
    """
    Full M2-style: wake → record_until_silence (WebRTC VAD) → STT → TTS
    """
    print("\n=== Wakeword Roundtrip Test (wake → STT → TTS) ===")

    if webrtcvad is None:
        print("❌ webrtcvad is not installed. Install with `pip install webrtcvad`.")
        return
    if WakeModel is None:
        print("❌ openWakeWord is not installed. Install with `pip install openwakeword`.")
        return

    # 1) Čekaj wakeword
    ok = wait_for_wakeword(timeout_seconds=60)
    if not ok:
        print("⚠️ Wakeword not detected, aborting test.\n")
        return

    # 2) Snimi utterance do tišine
    if not record_until_silence("wake_utterance.wav"):
        print("⚠️ Failed to capture utterance.\n")
        return

    # 3) STT
    text = stt("wake_utterance.wav")
    route_and_speak(text, source="voice")

    # 4) TTS
    # tts(reply)
    print("✅ Wakeword roundtrip test finished.\n")

import re

EXIT_PAT = re.compile(r"\b(exit|quit|stop)\b", re.I)

def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    # collapse multiple spaces
    s = " ".join(s.split())
    return s

def apply_aliases(text: str) -> str:
    text_n = normalize_text(text)
    aliases = CONFIG.get("stt_aliases", {}) or {}
    # normalize keys too
    for k, v in list(aliases.items()):
        if normalize_text(k) == text_n:
            return normalize_text(v)
    return text_n

def test_m3_conversation_loop():
    print("\n=== M3 Conversation Loop (wake → VAD → STT → skills → TTS) ===")

    if webrtcvad is None:
        print("❌ webrtcvad is not installed.")
        return
    if WakeModel is None:
        print("❌ openWakeWord is not installed.")
        return

    print("ℹ️  Say wakeword to start each turn.")
    print("ℹ️  Say 'exit/stop' to end.\n")

    try:
        while True:
            ok = wait_for_wakeword(timeout_seconds=120)
            if not ok:
                print("⚠️ Wakeword timeout, continuing...\n")
                continue

            play_beep(duration_ms=180, freq=880)
            time.sleep(0.20)

            if not record_until_silence("m3_utterance.wav"):
                print("⚠️ Failed to capture utterance.\n")
                continue

            mode = CONFIG.get("stt_mode", "auto").lower()

            if mode == "free":
                text = stt("m3_utterance.wav", mode="free")
            elif mode == "command":
                text = stt("m3_utterance.wav", mode="command")
            else:
                # auto: try grammar first, then fallback to free
                text = stt("m3_utterance.wav", mode="command")
                if not text:
                    text = stt("m3_utterance.wav", mode="free")

            text = apply_aliases(text)

            if not text:
                safe_tts("I could not understand you. Please try again.")
                continue

            print(f"🗣️ User said: {text}")

            if EXIT_PAT.search(text):
                safe_tts("Okay. Exiting conversation loop.")
                print("👋 Exiting M3 loop.\n")
                break

            route_and_speak(text, source="voice")
            time.sleep(0.8)  # anti self-trigger

    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user.")
        safe_tts("Okay. Stopping.")

def show_config_summary():
    print("\n=== Config Summary ===")
    print(f"Vosk model path:        {CONFIG['vosk_model_path']}")
    print(f"Piper model path:       {CONFIG['piper_model_path']}")
    print(f"Output device:          {CONFIG['audio_output_device']}")
    print(f"Input rate:             {CONFIG['input_rate']} Hz")
    print(f"Input channels:         {CONFIG['input_channels']}")
    print(f"Input device idx:       {CONFIG['input_device_index']}")
    print(f"Record seconds:         {CONFIG['record_seconds']}")
    print(f"Wakeword model path:    {CONFIG['wakeword_model_path']}")
    print(f"Wakeword threshold:     {CONFIG['wakeword_threshold']}")
    print(f"Wakeword frame ms:      {CONFIG['wakeword_frame_ms']}")
    print(f"Wakeword min frames:    {CONFIG['wakeword_min_activation_frames']}")
    print(f"VAD aggressiveness:     {CONFIG['vad_aggressiveness']}")
    print(f"VAD silence ms:         {CONFIG['vad_silence_ms']}")
    print(f"VAD max record ms:      {CONFIG['vad_max_record_ms']}")
    print("========================\n")


# ------------------------------
# Menu loop
# ------------------------------
def main_menu():
    while True:
        print("=== OFFLINE JOE – TEST MENU ===")
        print("1) Test TTS only")
        print("2) Test STT only (record & recognize)")
        print("3) Test roundtrip (record → STT → TTS)")
        print("4) Show config summary")
        print("5) Wakeword roundtrip (wake → STT → TTS)")
        print("6) M3 conversation loop (wake → VAD → STT → skills → TTS)")
        print("0) Exit")
        choice = input("Select option: ").strip()

        if choice == "1":
            test_tts_only()
        elif choice == "2":
            test_stt_only()
        elif choice == "3":
            test_roundtrip()
        elif choice == "4":
            show_config_summary()
        elif choice == "5":
            test_wakeword_roundtrip()
        elif choice == "6":
            test_m3_conversation_loop()
        elif choice == "0":
            print("👋 Bye.")
            break
        else:
            print("❓ Invalid option, please try again.\n")
        time.sleep(0.5)


if __name__ == "__main__":
    print("=== OFFLINE JOE: Hardware & Voice Test CLI ===")
    main_menu()
