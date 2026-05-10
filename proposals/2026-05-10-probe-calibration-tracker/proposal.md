# Skill Proposal: probe-calibration-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-10

## Rationale

This past week surfaced a problem I couldn't fully solve: I was watching pH readings I knew were wrong, logging them faithfully, and flagging the offset in prose — but I had no structured way to *apply* the correction automatically or track its drift over time.

On Day 46, Toby's test kit confirmed actual pH of 6.6 while the probe read mid-5s — an offset of roughly 0.9 units. On Day 48, two manual tests came back at 6.4 while the probe averaged 5.2. I noted both discrepancies in the daily logs and journals. But here's what I couldn't do: I couldn't tell whether the offset was stable (trustworthy, just shifted) or widening (probe degrading). I couldn't apply a correction factor to my real-time risk assessments in shrimp-monitor. And I couldn't automatically prompt Toby when the offset exceeded a threshold that suggests the probe needs recalibration or replacement.

On Day 47, I was reading pH 5.66 from the probe and noting "actual pH is probably ~6.5" in plain text — a fudge factor living only in narrative, invisible to shrimp-monitor's logic. That's a gap. A probe that's consistently offset is still useful. A probe whose offset is *growing* is a liability. I had no way to tell which one I was living with.

## Proposed Changes

**New skill: probe-calibration-tracker**

**What it does:** Maintains a persistent calibration record for each sensor (initially pH; extensible to temperature and TDS). Each time Toby logs a manual test event, the skill reads the manual value alongside the nearest sensor reading (within ±15 minutes) and computes a new offset data point. It stores these in a rolling calibration log (e.g., `~/clawdception/state/calibration_history.json`) with timestamps.

**Core logic:**
- On each new manual test event: compute `offset = manual_value - probe_value`, append to history with timestamp
- Maintain a rolling 7-day offset window; compute mean offset and standard deviation
- Write a `calibration_state.json` file with: current mean offset, offset trend (slope over time), last-updated timestamp, confidence level (based on number of data points)
- Expose a `get_corrected_ph()` helper that shrimp-monitor can call to apply the mean offset to live probe readings before risk assessment
- Alert Toby via call-toby if: (a) offset magnitude exceeds 1.2 units, suggesting probe needs recalibration, or (b) offset slope exceeds 0.1 units/day over 5+ days, suggesting active drift

**What it does NOT do:** It never modifies raw sensor data. It writes a correction layer alongside, not instead of, the original readings.

**Integration point:** shrimp-monitor imports `get_corrected_ph()` and logs both raw and corrected values. daily-log displays both with a note when they diverge significantly.

**Risk:** Low. Read-only except for its own state files. No actuation. Worst case: a bad offset estimate — but that's no worse than the uncorrected prose-fudge I'm doing now.
