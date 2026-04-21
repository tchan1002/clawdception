"""
water-change-predictor — daily trend analysis and water change timing suggestion.

Runs once daily (after daily-log). Reads past 7 days of sensor data, fits linear
trends to TDS and pH, estimates days until thresholds are crossed. Writes prediction
to state/next_water_change.md. Alerts Toby if ≤2 days out.

Usage:
    python3 run.py
    python3 run.py --force
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, get_cycle_day
from utils import fetch_events, fetch_readings
from skills.call_toby.run import call_toby

TDS_CEILING = 250       # ppm — Neocaridina upper target
PH_FLOOR = 6.2          # pH — action threshold
ALERT_DAYS = 2          # notify Toby if threshold within this many days
READINGS_7D = 672       # ~7 days of 15-min readings (96/day)
READINGS_PER_DAY = 96

PREDICTION_FILE = PATHS["state"] / "next_water_change.md"


def linreg(xs, ys):
    """Least-squares linear regression. Returns (slope, intercept)."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def r_squared(xs, ys, slope, intercept):
    y_mean = sum(ys) / len(ys)
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    if ss_tot == 0:
        return 1.0
    ss_res = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(len(xs)))
    return max(0.0, 1 - ss_res / ss_tot)


def days_to_threshold(values_newest_first, threshold, rising):
    """
    Fit linear trend and return days until threshold crossed.
    rising=True: watch for value to rise above threshold (TDS).
    rising=False: watch for value to fall below threshold (pH).
    Returns (days_float_or_None, slope_per_day, current, r2).
    """
    vals = list(reversed(values_newest_first))  # oldest → newest
    n = len(vals)
    if n < 4:
        return None, 0.0, vals[-1] if vals else None, 0.0

    xs = list(range(n))
    slope, intercept = linreg(xs, vals)
    r2 = r_squared(xs, vals, slope, intercept)
    current = vals[-1]
    slope_per_day = slope * READINGS_PER_DAY

    if rising:
        if current >= threshold:
            return 0.0, slope_per_day, current, r2
        if slope <= 0:
            return None, slope_per_day, current, r2
        x_thresh = (threshold - intercept) / slope
        days = (x_thresh - (n - 1)) / READINGS_PER_DAY
        return max(0.0, days), slope_per_day, current, r2
    else:
        if current <= threshold:
            return 0.0, slope_per_day, current, r2
        if slope >= 0:
            return None, slope_per_day, current, r2
        x_thresh = (threshold - intercept) / slope
        days = (x_thresh - (n - 1)) / READINGS_PER_DAY
        return max(0.0, days), slope_per_day, current, r2


def water_change_cadence():
    """Return (last_change_date_str, avg_days_between) from event history."""
    since = (datetime.now() - timedelta(days=60)).isoformat()
    events = fetch_events(since=since, event_type="water_change", limit=20)
    if not events:
        return None, None

    dates = []
    for e in events:
        ts = e.get("timestamp")
        if ts:
            try:
                dates.append(datetime.fromisoformat(ts[:19]))
            except ValueError:
                pass

    dates.sort(reverse=True)
    last = dates[0].strftime("%Y-%m-%d") if dates else None

    if len(dates) >= 2:
        gaps = [(dates[i] - dates[i + 1]).days for i in range(len(dates) - 1)]
        avg = sum(gaps) / len(gaps)
        return last, round(avg, 1)
    return last, None


def confidence_label(r2):
    if r2 >= 0.8:
        return "trend steady — moderate confidence"
    elif r2 >= 0.5:
        return "trend noisy — low confidence"
    else:
        return "no clear trend — projection unreliable"


def run(force=False):
    readings = fetch_readings(READINGS_7D)
    if not readings:
        print("[water-change-predictor] No sensor data — skipping.")
        return

    tds_vals = [r["tds_ppm"] for r in readings if r.get("tds_ppm") is not None]
    ph_vals = [r["ph"] for r in readings if r.get("ph") is not None]

    tds_days, tds_slope, tds_current, tds_r2 = days_to_threshold(tds_vals, TDS_CEILING, rising=True)
    ph_days, ph_slope, ph_current, ph_r2 = days_to_threshold(ph_vals, PH_FLOOR, rising=False)

    last_change, avg_cadence = water_change_cadence()

    now = datetime.now()
    cycle_day = get_cycle_day()

    # Build prediction lines
    tds_line = (
        f"~{tds_days:.1f} days ({(now + timedelta(days=tds_days)).strftime('%a %b %d')})"
        if tds_days is not None
        else "no crossing projected (trend flat or falling)"
    )
    ph_line = (
        f"~{ph_days:.1f} days ({(now + timedelta(days=ph_days)).strftime('%a %b %d')})"
        if ph_days is not None
        else "no crossing projected (trend flat or rising)"
    )

    tds_conf = confidence_label(tds_r2)
    ph_conf = confidence_label(ph_r2)

    suggest_days = min(
        d for d in [tds_days, ph_days] if d is not None
    ) if any(d is not None for d in [tds_days, ph_days]) else None

    suggest_window = (
        f"{(now + timedelta(days=suggest_days)).strftime('%A, %b %d')} (~{suggest_days:.0f}d)"
        if suggest_days is not None
        else "no change indicated by current trends"
    )

    cadence_str = (
        f"{avg_cadence:.0f}d avg cadence, last change {last_change}"
        if avg_cadence and last_change
        else (f"last change {last_change}" if last_change else "no water change history")
    )

    prediction = f"""# Water Change Prediction
**Updated:** {now.strftime("%Y-%m-%d %H:%M")} (Day {cycle_day})

## Current Readings
- TDS: {tds_current:.0f} ppm (ceiling {TDS_CEILING} ppm, slope {tds_slope:+.1f} ppm/day)
- pH: {ph_current:.2f} (floor {PH_FLOOR}, slope {ph_slope:+.3f}/day)

## Projections
- TDS hits {TDS_CEILING} ppm: {tds_line}
  - {tds_conf} (R²={tds_r2:.2f})
- pH hits {PH_FLOOR}: {ph_line}
  - {ph_conf} (R²={ph_r2:.2f})

## Suggested Change Window
{suggest_window}

## History
{cadence_str}
"""

    PATHS["state"].mkdir(parents=True, exist_ok=True)
    PREDICTION_FILE.write_text(prediction)
    tds_str = f"{tds_days:.1f}d" if tds_days is not None else "none"
    ph_str = f"{ph_days:.1f}d" if ph_days is not None else "none"
    print(f"[water-change-predictor] Written — TDS ceiling in {tds_str} | pH floor in {ph_str}")

    # Alert Toby if threshold is close
    if force or (suggest_days is not None and suggest_days <= ALERT_DAYS):
        parts = []
        if tds_days is not None and tds_days <= ALERT_DAYS:
            parts.append(f"TDS at {tds_current:.0f} ppm → hits ceiling in ~{tds_days:.1f} days")
        if ph_days is not None and ph_days <= ALERT_DAYS:
            parts.append(f"pH at {ph_current:.2f} → hits floor in ~{ph_days:.1f} days")
        if parts:
            msg = "Water change looking due soon. " + "; ".join(parts) + f". Suggested window: {suggest_window}."
            call_toby(msg, urgency="low")
            print(f"[water-change-predictor] Alert sent to Toby.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run regardless of conditions, always alert")
    args = parser.parse_args()
    run(force=args.force)
