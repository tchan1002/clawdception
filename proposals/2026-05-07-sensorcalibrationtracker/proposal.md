# Skill Proposal: sensor_calibration_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-07

## Rationale

Twice in the past week, sensor readings told a story the tank wasn't actually living. On Day 44 (May 4), the probe dislodgement went undetected for an unknown duration — the journal notes "what looked like a sharp shift" before Toby logged the physical cause. On Day 46 (May 6), the daily log opens with the striking line: "the sensor has been lying" — confirmed by Toby's test kit showing pH 6.6 while the probe was reporting values in the mid-5s. Both times, I was reasoning from corrupted data without knowing it. I flagged the Day 43 pH low of 6.19 with "texture" in the log, and now I suspect that reading was also drifted. I have no systematic way to notice when sensor output diverges from physical reality, no memory of when the probe was last verified against a reference, and no mechanism to flag growing suspicion before Toby happens to run a manual test. The gap isn't alerting on bad readings — it's not knowing the readings have gone bad in the first place. A skill that tracks manual test events, computes sensor-vs-kit delta, remembers calibration history, and raises a soft flag when the probe hasn't been cross-checked in a while would have changed my confidence level on pH readings as far back as Day 43.

## Proposed Changes

New skill: **sensor-calibration-tracker**

**Purpose:** Maintains a running record of sensor accuracy by comparing probe readings against Toby's manual test kit entries. Raises a soft advisory when calibration confidence is low.

**When it runs:** Event-driven — triggered when a "manual_test" event is logged (via telegram-listener or Toby's manual log entry). Also runs a passive daily check at 7:10 AM (after daily-log) to assess how stale the last calibration verification is.

**Core logic:**

1. **On manual test logged:** Reads the logged kit values (pH, ammonia, nitrite, nitrate if provided). Fetches the sensor reading nearest in time (within ±15 min). Computes delta: `kit_pH − probe_pH`. Appends entry to `calibration_log.json` with timestamp, delta, and drift direction.

2. **Drift threshold:** If the rolling 3-reading average delta exceeds ±0.3 pH units, writes a `CALIBRATION_DRIFT` decision log entry and notifies Toby via call-toby at `advisory` urgency: "Probe is reading [X] units [low/high] vs. kit. Consider recalibration."

3. **Staleness check (daily):** If no manual test has been logged in 10+ days, appends a soft reminder to the daily-log context so the morning write-up can mention it naturally. Does NOT send a Telegram nag — that's auto-feeder's job; this is ambient awareness.

4. **State file:** Writes `calibration_state.json` with: last verified date, last delta, rolling average delta, confidence flag (`good` / `drifting` / `unknown`). shrimp-monitor reads this flag and notes low confidence in its risk assessments.

**Risk rationale:** Read-only except for calling call-toby at advisory level. No tank intervention. The main risk is a false drift flag if Toby's kit reading and the probe timestamp are mismatched — mitigated by the ±15 min window and requiring 3-reading consensus before alerting.
