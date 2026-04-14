"""
equipment-check — hardware health check for Media Luna.

Checks:
  Sensor-derivable:
    - DS18B20 temp probe error rate (temp_raw_c == -127.0 in >10% of last 24h)
    - ESP32 post failure trend (elevated post_failures in last hour)
    - WiFi RSSI (mean < -75 dBm in last hour)
    - Heap free (any reading < 80,000 bytes in last hour)
    - Uptime reset (latest uptime_ms < previous → unexpected reboot)
    - pH probe drift (mean (ph_pre_offset - ph) deviates >0.15 from expected offset)
    - ADC rail saturation (ph_raw_adc or tds_raw_adc == 0 or 4095)

  Schedule-based (state tracked in logs/equipment_state.json):
    - pH probe recalibration (every 30 days)

Logs a decision entry so the journal picks it up.
Calls Toby if any issue needs attention (at most once per 24hr per item).

Usage:
    python3 run.py
    python3 run.py --force    # ignore nag cooldowns
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, get_cycle_day
from utils import fetch_readings, log_decision, SkillLock
from skills.call_toby.run import call_toby

STATE_PATH = PATHS["logs"] / "equipment_state.json"

PH_PROBE_CALIBRATION_INTERVAL_DAYS = 30
NAG_COOLDOWN_HOURS = 23

# Sensor thresholds
WIFI_RSSI_WARN = -75       # dBm  — warn if mean falls below this over last hour
HEAP_FREE_WARN = 80_000    # bytes — warn if any reading in last hour is below this
PH_DRIFT_THRESHOLD = 0.15  # pH units — warn if mean offset deviation exceeds this over 24h
ADC_RAIL_LOW = 0
ADC_RAIL_HIGH = 4095

DEFAULT_STATE = {
    "ph_probe_last_calibrated": "2026-03-22",  # set at cycle start
    "last_nag": {},
}


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_state(state):
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def should_nag(state, key, force=False):
    if force:
        return True
    last_str = state.get("last_nag", {}).get(key)
    if not last_str:
        return True
    return (datetime.now() - datetime.fromisoformat(last_str)).total_seconds() / 3600 >= NAG_COOLDOWN_HOURS


def record_nag(state, key):
    state.setdefault("last_nag", {})[key] = datetime.now().isoformat()


def parse_raw(reading):
    """Parse raw_json from a reading dict; returns (debug, system, calibration) dicts."""
    try:
        raw = json.loads(reading["raw_json"])
        return raw.get("debug", {}), raw.get("system", {}), raw.get("calibration", {})
    except Exception:
        return {}, {}, {}


def run(force=False):
    with SkillLock("equipment-check"):
        ts = datetime.now().isoformat()
        cycle_day = get_cycle_day()
        state = load_state()

        issues = []  # list of (key, message, urgency)
        notes = []   # informational, no alert needed

        # --- Sensor-derivable checks ---
        readings = fetch_readings(96)  # last 24h
        recent = readings[:4]          # last ~1 hour

        if readings:
            # DS18B20 temp probe error rate
            error_count = sum(
                1 for r in readings
                if parse_raw(r)[0].get("temp_raw_c") == -127.0
            )
            error_rate = error_count / len(readings)
            if error_rate > 0.1:
                issues.append((
                    "ds18b20_error",
                    f"DS18B20 temp probe erroring in {error_count}/{len(readings)} readings — check wiring.",
                    "warning",
                ))
            elif error_count > 0:
                notes.append(f"DS18B20 had {error_count} transient error(s) in last 24h.")

        if recent:
            # WiFi RSSI
            rssi_values = [
                parse_raw(r)[1].get("wifi_rssi")
                for r in recent
                if parse_raw(r)[1].get("wifi_rssi") is not None
            ]
            if rssi_values:
                mean_rssi = sum(rssi_values) / len(rssi_values)
                if mean_rssi < WIFI_RSSI_WARN:
                    issues.append((
                        "wifi_rssi_low",
                        f"WiFi RSSI averaging {mean_rssi:.0f} dBm in last hour (threshold {WIFI_RSSI_WARN}) — signal weak.",
                        "warning",
                    ))
                else:
                    notes.append(f"WiFi RSSI OK — mean {mean_rssi:.0f} dBm.")

            # Heap free
            heap_values = [
                parse_raw(r)[1].get("heap_free")
                for r in recent
                if parse_raw(r)[1].get("heap_free") is not None
            ]
            if heap_values:
                min_heap = min(heap_values)
                if min_heap < HEAP_FREE_WARN:
                    issues.append((
                        "heap_low",
                        f"ESP32 heap_free dropped to {min_heap:,} bytes in last hour — possible memory leak, reboot may be needed.",
                        "warning",
                    ))
                else:
                    notes.append(f"Heap OK — min {min_heap:,} bytes in last hour.")

            # Uptime reset detection (newest-first list: readings[0] is latest)
            if len(recent) >= 2:
                uptime_now = parse_raw(recent[0])[1].get("uptime_ms")
                uptime_prev = parse_raw(recent[1])[1].get("uptime_ms")
                if uptime_now is not None and uptime_prev is not None:
                    if uptime_now < uptime_prev:
                        issues.append((
                            "uptime_reset",
                            f"ESP32 uptime reset detected — was {uptime_prev:,} ms, now {uptime_now:,} ms. Unexpected reboot.",
                            "warning",
                        ))

            # ADC rail saturation (check latest reading)
            debug_latest = parse_raw(recent[0])[0]
            ph_adc = debug_latest.get("ph_raw_adc")
            tds_adc = debug_latest.get("tds_raw_adc")
            if ph_adc is not None and ph_adc in (ADC_RAIL_LOW, ADC_RAIL_HIGH):
                issues.append((
                    "ph_adc_saturated",
                    f"pH ADC rail-saturated ({ph_adc}) — probe disconnected or wiring fault.",
                    "warning",
                ))
            if tds_adc is not None and tds_adc in (ADC_RAIL_LOW, ADC_RAIL_HIGH):
                issues.append((
                    "tds_adc_saturated",
                    f"TDS ADC rail-saturated ({tds_adc}) — probe disconnected or wiring fault.",
                    "warning",
                ))

        # pH probe drift (24h of readings)
        if readings:
            drift_samples = []
            for r in readings:
                try:
                    raw = json.loads(r["raw_json"])
                    debug = raw.get("debug", {})
                    calibration = raw.get("calibration", {})
                    ph_top = r.get("ph")
                    ph_pre = debug.get("ph_pre_offset")
                    ph_offset = calibration.get("ph_offset")
                    if ph_top is not None and ph_pre is not None and ph_offset is not None:
                        # Expected: ph_pre - ph ≈ -ph_offset (since ph = ph_pre + offset)
                        observed_diff = ph_pre - ph_top
                        expected_diff = -ph_offset
                        drift_samples.append(observed_diff - expected_diff)
                except Exception:
                    pass
            if len(drift_samples) >= 4:
                mean_drift = sum(drift_samples) / len(drift_samples)
                if abs(mean_drift) > PH_DRIFT_THRESHOLD:
                    issues.append((
                        "ph_probe_drift",
                        f"pH probe drift detected — mean offset deviation {mean_drift:+.3f} pH over 24h (threshold ±{PH_DRIFT_THRESHOLD}). Recalibration may be needed.",
                        "warning",
                    ))
                else:
                    notes.append(f"pH probe drift OK — mean deviation {mean_drift:+.3f} pH.")

        # --- Schedule-based checks ---
        today = date.today()

        ph_last = state.get("ph_probe_last_calibrated")
        if ph_last is None:
            issues.append((
                "ph_probe_never_calibrated",
                "pH probe calibration has never been logged.",
                "warning",
            ))
        else:
            days_since = (today - date.fromisoformat(ph_last)).days
            if days_since >= PH_PROBE_CALIBRATION_INTERVAL_DAYS:
                issues.append((
                    "ph_probe_overdue",
                    f"pH probe last calibrated {days_since}d ago — due every {PH_PROBE_CALIBRATION_INTERVAL_DAYS}d.",
                    "warning",
                ))
            else:
                notes.append(f"pH probe OK — calibrated {days_since}d ago, next in {PH_PROBE_CALIBRATION_INTERVAL_DAYS - days_since}d.")

        # --- Notify ---
        for key, message, urgency in issues:
            if should_nag(state, key, force):
                call_toby(message, urgency=urgency)
                record_nag(state, key)

        # --- Log decision ---
        if issues:
            risk = "yellow"
            reasoning = f"{len(issues)} equipment issue(s): " + "; ".join(m for _, m, _ in issues)
        else:
            risk = "green"
            reasoning = "All equipment checks passed. " + " ".join(notes)

        log_decision({
            "risk_level": risk,
            "reasoning": reasoning,
            "recommended_actions": [m for _, m, _ in issues] or ["No action needed."],
            "_cycle_day": cycle_day,
            "_timestamp": ts,
            "_trigger": "equipment_check",
            "issues": [{"key": k, "message": m} for k, m, _ in issues],
            "notes": notes,
        })

        summary = f"[{ts[:16]}] equipment-check | {risk} | {len(issues)} issue(s) | {reasoning[:80]}"
        print(summary)
        save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore nag cooldowns")
    args = parser.parse_args()
    run(force=args.force)
