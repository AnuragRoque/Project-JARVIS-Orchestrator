"""Read the machine's power state: battery %, charging, time left, power plan."""
from __future__ import annotations

import subprocess

from jarvis.app.logsetup import get_logger

log = get_logger("power.status")
_NO_WINDOW = 0x08000000


def get_status() -> dict:
    """Return a compact, speak-friendly snapshot of the power state."""
    out: dict = {"has_battery": False}

    try:
        import psutil
        batt = psutil.sensors_battery()
    except Exception:
        batt = None

    if batt is not None:
        out["has_battery"] = True
        out["percent"] = round(batt.percent)
        out["plugged_in"] = bool(batt.power_plugged)
        out["time_left"] = _fmt_secs(batt.secsleft, batt.power_plugged)
        out["summary"] = _battery_summary(out)
    else:
        out["summary"] = "This PC has no battery (desktop / on AC power)."

    plan = _active_power_plan()
    if plan:
        out["power_plan"] = plan
    return out


def _battery_summary(o: dict) -> str:
    pct = o["percent"]
    if o["plugged_in"]:
        state = "charging" if pct < 100 else "fully charged"
        return f"Battery at {pct}% and {state}."
    left = o.get("time_left")
    tail = f", about {left} remaining" if left else ""
    return f"Battery at {pct}%, on battery power{tail}."


def _fmt_secs(secs, plugged) -> str | None:
    # psutil returns POWER_TIME_UNLIMITED (-1) / POWER_TIME_UNKNOWN (-2).
    if plugged or secs is None or secs < 0:
        return None
    h, m = divmod(secs // 60, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _active_power_plan() -> str | None:
    try:
        res = subprocess.run(
            ["powercfg", "/getactivescheme"],
            creationflags=_NO_WINDOW, capture_output=True, text=True, timeout=5)
        line = (res.stdout or "").strip()
        # e.g. "Power Scheme GUID: 381b... (Balanced)"
        if "(" in line and ")" in line:
            return line[line.rfind("(") + 1:line.rfind(")")]
    except Exception:
        log.debug("power plan lookup failed", exc_info=True)
    return None
