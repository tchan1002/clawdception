# Skill Proposal: ph_calibration_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-11

## Rationale

This past week exposed a quiet but significant gap: I've been living with a pH probe that lies, and I have no formal memory of how much it lies, or whether that lie is changing over time.

On Day 46, Toby confirmed via test kit that actual pH was 6.6 while the probe read somewhere in the mid-5s — a ~0.9 unit offset. On Day 48, two manual tests both returned 6.4 while the probe averaged 5.2. I've been carrying a mental note that the probe runs "about 0.9 low," but that offset lives nowhere persistent. It's been threaded into daily-log narrative and journal commentary, but it isn't tracked, it isn't trended, and it isn't automatically applied.

This matters because I can't tell whether the offset is stable or drifting. A probe that's consistently 0.9 low is manageable. A probe whose offset is slowly growing — or erratically shifting — is a different problem entirely. I've been noting this in prose but doing nothing structural with it. On Day 48, I wrote "that's not drift, that's not measurement noise" — and I was right. But I had no tool to quantify *how* not-drift it was, or whether it was getting worse. A dedicated calibration tracker would let me answer that question, and let shrimp-monitor apply a corrected pH value in its risk assessments rather than reasoning around a known-bad number.

## Proposed Changes

**New skill: ph-calibration-tracker**

**What it does:**
Maintains a persistent calibration record for the pH probe by logging every manual test result alongside the concurrent probe reading. Computes and stores the rolling offset (manual − probe), tracks offset trend over time, and surfaces a corrected pH value for use by other skills.

**Data it maintains** (written to `~/clawdception/state/ph_calibration.json`):
- Array of calibration events: `{timestamp, manual_ph, probe_ph, offset}`
- `current_offset`: median of the last 5 calibration events (robust to outliers)
- `offset_trend`: linear slope of offset over time (units/day) — is the probe drifting?
- `corrected_ph`: most recent probe reading + current_offset
- `last_calibrated`: timestamp of most recent manual test
- `calibration_age_days`: how long since last manual test

**How it's triggered:**
- Passively: whenever a manual event of type `water_test` is logged with a pH value, ph-calibration-tracker runs automatically to ingest the new data point
- On demand: callable from telegram-listener if Toby texts a manual pH reading directly

**What other skills get:**
- `shrimp-monitor` reads `corrected_ph` from the calibration state file instead of raw probe pH — risk assessments are based on chemistry that's actually happening, not probe fiction
- `daily-log` receives `current_offset` and `offset_trend` and can note if the probe is drifting (e.g., "offset has grown 0.15 units in the past 10 days — calibration recommended")
- If `offset_trend` exceeds 0.05 units/day sustained over 5+ days, skill flags probe degradation via `call-toby`
- If `calibration_age_days` exceeds 7, daily-log includes a gentle nudge to Toby to run a manual test

**Risk controls:**
- Read-only with respect to tank hardware — no actuation
- Never overwrites raw sensor data; corrected values are stored separately
- If fewer than 2 calibration events exist, corrected_ph defaults to raw probe value with a logged caveat
