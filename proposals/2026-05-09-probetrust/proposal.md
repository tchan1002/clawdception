# Skill Proposal: probe_trust

**Type:** new
**Risk Level:** medium
**Date:** 2026-05-09

## Rationale

This past week exposed a gap that kept quietly frustrating me: I have no formal way to reason about whether my own sensor data is trustworthy at any given moment. On Day 44, a temperature probe dislodgement went undetected for an unknown duration — I was logging pH readings I couldn't actually trust, and I didn't know it. On Days 46–48, the pH probe turned out to be reading ~0.9 units low relative to Toby's test kit, a discrepancy I could only flag narratively, not structurally. In both cases, shrimp-monitor kept running its 15-minute heartbeat against numbers that were quietly wrong. It assessed risk using bad inputs and I had no mechanism to say "hold on — discount these readings." More acutely: on Day 48, the auto-feeder kept flagging the 72-hour feeding gap, and shrimp-monitor kept noting the elevated concern — but neither could contextualize that the probe values underpinning their risk scores were under active investigation. A probe-trust layer — something that tracks known sensor anomalies, manual calibration offsets, and physical dislodgement events, and propagates that uncertainty to downstream skills — would have changed my Day 44 and Day 46 risk assessments materially. Right now I observe sensor problems. I just can't do anything about them.

## Proposed Changes

**New skill: probe-trust**

A lightweight sensor confidence registry that sits between raw sensor data and the skills that consume it.

**What it does:**
- Maintains a small state file (`probe_trust_state.json`) with a confidence record per sensor: `{sensor_id, confidence_level [high/degraded/suspended], reason, since_timestamp, manual_offset}`
- Listens for three trigger types:
  1. **Manual event logs** — when Toby logs a dislodgement, recalibration, or test-kit discrepancy, probe-trust updates the relevant sensor's confidence level and reason string
  2. **Automated anomaly detection** — if shrimp-monitor detects a step-change discontinuity (e.g., pH drops >1.0 units in a single 15-min interval without a logged water change), probe-trust is notified and sets that sensor to `degraded`
  3. **Manual calibration events** — when Toby logs a test-kit result, probe-trust calculates and stores the offset (e.g., `pH_offset: +0.9`) and marks the sensor `degraded_with_offset`

**How downstream skills use it:**
- shrimp-monitor reads probe-trust state before risk assessment; if a sensor is `degraded`, it appends a caveat to its risk log and adjusts confidence in that parameter's contribution to the overall risk score
- daily-log reads probe-trust state and surfaces any active sensor caveats in the "Tank Right Now" section
- shrimp-alert checks probe-trust before firing; a `suspended` sensor cannot alone trigger a critical alert (requires corroboration from another parameter or a manual event)

**What it does NOT do:**
- Never modifies raw sensor data
- Never suppresses alerts entirely — it annotates and contextualizes, it does not silence
- No actuation; purely read/write to state files and logs

**Run cadence:** Event-driven (triggered by shrimp-monitor and telegram-listener parsing manual events), plus a daily summary written to the journal.
