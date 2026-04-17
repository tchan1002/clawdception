# Skill Proposal: sensor_calibration_watch

**Type:** new
**Risk Level:** low
**Date:** 2026-04-17

## Rationale

On Day 24 (April 14th), something stopped me cold: Toby's manual test logged pH 7.0 at 22:14, while my sensor was reading 6.34 at that exact moment. That's a 0.66-unit gap — not drift, not noise, not a post-water-change transient. That's a sensor and a test kit looking at the same water and disagreeing about fundamental reality. I flagged it in the journal and moved on, because that's all I could do. I had no framework for deciding which reading to trust, no history of how often this happens, and no way to weight my own sensor confidence when generating risk assessments. For the next 48 hours, every pH reading I reported carried an unspoken asterisk I couldn't quantify. The shrimp were new, the cycle was live, and my most important water quality signal was operating under unknown reliability. This isn't a one-time problem — manual tests are episodic ground truth, and right now they just disappear into the log without being used to validate or flag sensor drift. A dedicated calibration-watch skill would track the delta between manual test results and sensor readings over time, build a divergence history, and alert when that gap exceeds a threshold. It would also feed a confidence flag into shrimp-monitor so that risk assessments can honestly reflect when the sensor data they're built on is suspect.

## Proposed Changes

Create a new skill: `sensor-calibration-watch`.

**Trigger:** Runs whenever a manual water test is logged by Toby (via telegram-listener or manual event log). Also runs a weekly summary every Sunday at 7:10 AM.

**What it does:**

1. **Delta logging:** When a manual test result is received, looks up the nearest sensor reading within a ±15-minute window. Records the delta (manual minus sensor) for each overlapping parameter (pH, temperature, TDS) into a persistent file: `~/clawdception/state/calibration_history.json`.

2. **Drift detection:** If the rolling average delta for any parameter — calculated over the last 5 paired readings — exceeds a defined threshold (suggested: pH ±0.3, temp ±1.5°F, TDS ±15 µS/cm), writes a calibration-warning entry to the decision log and calls call-toby with `medium` urgency, noting which sensor is drifting and by how much.

3. **Confidence flag:** Writes a sensor confidence field to `~/clawdception/state/tank_state.json` for each monitored parameter: `high` (delta within threshold), `degraded` (delta approaching threshold), or `unreliable` (delta exceeds threshold or no manual pairing in 7+ days). shrimp-monitor reads this flag and includes it in Claude's risk assessment prompt — e.g., "Note: pH sensor confidence is currently DEGRADED based on recent manual test divergence."

4. **Weekly summary:** Posts a brief calibration health note in the Sunday daily log — how many paired readings were collected, average deltas, and current confidence levels.

**Files touched:** `calibration_history.json` (new), `tank_state.json` (new confidence fields), decision log (warnings only).

**Risk rationale:** Read-only relative to sensor hardware. Worst case is a spurious calibration warning that Toby dismisses. No actuation involved.
