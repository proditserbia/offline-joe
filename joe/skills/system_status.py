from __future__ import annotations
import logging
import platform, os, time, socket
import psutil
from .base import SkillContext, SkillResult
from ..utils.shell import has_cmd, run

log = logging.getLogger(__name__)


def _cpu_temp() -> float | None:
    # Raspberry Pi: vcgencmd measure_temp
    if has_cmd("vcgencmd"):
        cp = run(["vcgencmd", "measure_temp"])
        if cp.returncode == 0 and "temp=" in cp.stdout:
            try:
                return float(cp.stdout.strip().split("temp=")[1].split("'")[0])
            except Exception:
                return None
    # Linux thermal zones fallback
    try:
        for path in ("/sys/class/thermal/thermal_zone0/temp",):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return float(f.read().strip()) / 1000.0
    except Exception:
        pass
    return None

def _ssd_usage(mount: str = "/mnt/ssd") -> psutil._common.sdiskusage | None:
    """Return disk usage for the NVMe SSD mount, or None if not mounted."""
    try:
        if os.path.ismount(mount):
            return psutil.disk_usage(mount)
    except Exception as exc:
        log.debug("SSD disk usage unavailable at %s: %s", mount, exc)
    return None


def _ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _fmt_uptime(uptime_s: int) -> str:
    h = uptime_s // 3600
    m = (uptime_s % 3600) // 60
    if h <= 0:
        return f"{m} minutes"
    if m == 0:
        return f"{h} hours"
    return f"{h} hours {m} minutes"

_NUM_WORDS_0_19 = [
    "zero", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen"
]

_TENS = [
    "", "", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety"
]


def _spoken_number(n: int) -> str:
    if n < 20:
        return _NUM_WORDS_0_19[n]
    if n < 100:
        tens, rest = divmod(n, 10)
        return _TENS[tens] if rest == 0 else f"{_TENS[tens]} {_NUM_WORDS_0_19[rest]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        if rest == 0:
            return f"{_NUM_WORDS_0_19[hundreds]} hundred"
        return f"{_NUM_WORDS_0_19[hundreds]} hundred {_spoken_number(rest)}"
    return str(n)


def _spoken_ip(ip: str) -> str:
    parts = ip.split(".")
    spoken = [_spoken_number(int(p)) for p in parts]
    return " dot ".join(spoken)

class SystemStatusSkill:
    name = "system_status"
    description = "CPU/RAM/Disk/Uptime/Temp/IP status."

    def __init__(self, ssd_mount: str = "/mnt/ssd") -> None:
        self.ssd_mount = ssd_mount

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        load1, load5, load15 = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
        uptime_s = int(time.time() - psutil.boot_time())
        temp = _cpu_temp()
        ip = _ip()
        host = platform.node()
        ssd = _ssd_usage(self.ssd_mount)

        uptime_spoken = _fmt_uptime(uptime_s)

        msg = (
            f"{host}. CPU load is {load1:.2f}. "
            f"Memory is {vm.percent:.0f} percent. "
            f"Disk usage is {du.percent:.0f} percent. "
            f"Uptime is {uptime_spoken}."
        )

        if ssd is not None:
            msg += f" S S D usage is {ssd.percent:.0f} percent."
        if temp is not None:
            msg += f" CPU temperature is {temp:.1f} degrees."
        if ip:
            msg += f" IP address is {_spoken_ip(ip)}."

        data: dict = {
            "host": host,
            "load1": load1,
            "ram_percent": vm.percent,
            "disk_percent": du.percent,
            "uptime_s": uptime_s,
            "temp_c": temp,
            "ip": ip,
        }
        if ssd is not None:
            data["ssd_mount"] = self.ssd_mount
            data["ssd_percent"] = ssd.percent
            data["ssd_free_gb"] = round(ssd.free / (1024 ** 3), 1)

        log.debug("SystemStatus: %s", data)
        return SkillResult(True, msg, data=data)
