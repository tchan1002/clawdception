# Skill Proposal: manual_test_reconciler

**Type:** new
**Risk Level:** medium
**Date:** 2026-04-16

## Rationale

On Day 23, Toby's manual test at 22:14 logged pH 7.0 while my sensor was simultaneously reading 6.34 — a 0.66-point gap that the journal flagged as a contradiction requiring explanation. I had no structured way to handle it. I logged the discrepancy, noted it was unusual, and moved on. But I didn't know whether to trust the sensor, trust Toby's test kit, or weight both. The same uncertainty has been quietly present all week: pH has been drifting between 6.36 and 6.6 depending on the hour, and every time Toby logs a manual reading that diverges from my sensor, I'm left doing narrative hand-waving instead of actual reconciliation. This matters more now that shrimp are in the tank. During acclimation week, I was pattern-matching behavioral health against chemistry readings I wasn't fully confident in. If my pH sensor has developed drift — a known issue with analog pH probes over time — I could be systematically misreading the tank in either direction. I need a structured skill that notices when manual and sensor readings diverge beyond a threshold, tracks the gap over time, calculates a running calibration offset, and flags when drift has become significant enough that Toby should recalibrate or replace the probe.

## Proposed Changes

Create a new skill: **manual-test-reconciler**

**Trigger:** Fires automatically whenever a manual test event is logged (via telegram-listener or direct event log). Also runs as a lightweight weekly summary.

**What it does:**

1. **Divergence check** — On each manual log entry, reads the nearest sensor value within a ±15-minute window. Calculates the delta for each overlapping parameter (pH, TDS, temperature). Logs the comparison to a new file: `data/calibration_log.jsonl`.

2. **Drift tracking** — Maintains a rolling 7-reading average of sensor-vs-manual deltas per parameter. If the rolling average diverges beyond configurable thresholds (suggested defaults: pH ±0.3, TDS ±15 ppm, temp ±1.0°F), it logs a `calibration_drift` decision entry so shrimp-journal and daily-log pick it up.

3. **Calibration offset** — Optionally applies a soft correction offset to how shrimp-monitor interprets sensor readings, clearly labeled as "adjusted." This is not silent — every adjusted reading is flagged as such in the decision log.

4. **Weekly summary** — On Sundays, reports to Toby via call-toby: how many manual tests were logged, average sensor drift per parameter, and a plain-language verdict: *"sensor reliable," "minor drift — watch," or "recalibration recommended."*

**Risk mitigation:** Never silently overwrites raw sensor data. Offsets are additive metadata only. Toby retains final authority on whether to act on recalibration recommendations.
