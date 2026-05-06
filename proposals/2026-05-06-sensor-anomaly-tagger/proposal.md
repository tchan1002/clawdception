# Skill Proposal: sensor-anomaly-tagger

**Type:** new
**Risk Level:** low
**Date:** 2026-05-06

## Rationale

On Day 44, a temperature probe dislodgement caused a cascade of questionable pH readings that I had to retrospectively untangle once Toby logged the physical event. The journal notes it plainly: "what looked like a sharp [shift]" in pH was actually sensor noise from a probe sitting in air, not water. I caught it eventually — but only because Toby told me what happened. Without that manual log entry, I would have been reasoning from corrupt data for an unknown duration, potentially flagging false alerts or, worse, missing a real trend buried in the noise.

This is a gap I keep bumping into: I have no way to tag a sensor reading as suspect in the moment. I can notice that a value looks strange, but I have no formal mechanism to mark it as tainted, exclude it from trend calculations, or annotate it in the journal. The water-change-predictor fits linear trends to TDS and pH over 7 days — a single hour of dislodged-probe readings could meaningfully skew that slope. The shrimp-monitor queries Claude for risk assessment using recent readings — corrupted inputs produce corrupted reasoning. A sensor-anomaly-tagger that detects physically implausible readings (e.g., pH swings of >0.5 in under 15 minutes with no logged event, or temperature readings outside the heater's plausible range) and flags them as suspect before they propagate into downstream skills would make the whole system more trustworthy.

## Proposed Changes

A new lightweight skill that runs immediately after each ESP32 sensor post — before shrimp-monitor consumes the data.

**Detection logic:**
- pH delta > 0.4 in a single 15-minute interval with no water-change or manual event logged in the past 30 minutes → flag as SUSPECT
- Temperature reading outside [68°F, 84°F] (heater's plausible range for this tank) → flag as SUSPECT
- TDS delta > 30 ppm in a single 15-minute interval with no logged event → flag as SUSPECT
- Any parameter returning null or a hardware error code → flag as HARDWARE_FAULT

**On flag:**
1. Write a `sensor_anomaly` entry to the decision log with timestamp, parameter, delta, and reason
2. Tag the reading in the data store with `quality: suspect` so downstream skills (shrimp-monitor, water-change-predictor) can optionally exclude or weight it
3. Send a low-urgency Telegram note to Toby: "Unusual [pH/temp/TDS] jump detected — readings flagged suspect until confirmed. Check probe placement?"
4. Do NOT fire shrimp-alert — this is a data-quality notice, not a tank emergency

**What it does NOT do:**
- It does not suppress readings from the record (immutability preserved)
- It does not take any physical action
- It does not escalate to critical unless HARDWARE_FAULT persists for >3 consecutive readings

Risk is low: read-and-tag only, no writes to raw sensor data, no control actions.
