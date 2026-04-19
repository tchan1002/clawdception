# Skill Proposal: cycle_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-19

## Rationale

For 29 days I have been watching the nitrogen cycle progress with no dedicated memory for it. Every entry in this past week's journals gestures at cycle state — "nearing completion," "biofilm bloom phase," "still progressing" — but each of those assessments is reconstructed from scratch, inference layered on inference, with no structured model underneath. On Day 22, I noticed a quiet temperature concern and organic accumulation but had no framework for saying *where* in the cycle we were or what to expect next. On Day 25, unplanned snails appeared and I had no mechanism to note that a biologically active tank mid-cycle is exactly the environment where hitchhikers thrive — and that their presence might itself be cycle-stage data. On Day 26, Toby's 60-photograph session captured a green filamentous algae bloom I identified but could not contextualize against cycle stage. The shrimp arrived on Day 23 before the cycle completed — a calculated risk — and I have been watching ammonia, nitrite, and nitrate trends without a skill dedicated to synthesizing them into a cycle completion estimate. This gap means my daily logs describe the cycle impressionistically rather than tracking it as the primary health event it is. I need a skill that owns this problem explicitly.

## Proposed Changes

A new skill called `cycle_tracker` that runs once daily, immediately before `daily_log` (e.g., 6:45 AM), and maintains a structured cycle state file at `~/clawdception/state/cycle_state.json`.

**What it tracks:**
- Current estimated cycle phase: `seeding`, `ammonia_peak`, `nitrite_rise`, `nitrite_crash`, `establishing`, or `complete`
- Rolling 7-day history of manual ammonia/nitrite/nitrate test results (ingested from Toby's logged manual events)
- Sensor-derived proxy signals: pH trend direction, TDS drift rate, temperature stability — all of which correlate loosely with cycle phase transitions
- A "cycle confidence score" (low/medium/high) reflecting how much manual test data has been logged recently vs. how much the agent is inferring from sensor proxies

**What it produces:**
- Updates `cycle_state.json` with current phase, confidence, and a one-sentence human-readable summary
- Writes a decision log entry so `shrimp_journal` and `daily_log` can incorporate it naturally
- If confidence is low (no manual test in 5+ days during active cycle), writes a gentle reminder flag for `call_toby` to prompt a test — not an alert, just a nudge
- On detecting phase transition (e.g., nitrite crash suggesting completion), flags this as a notable event for the daily log narrative

**What it explicitly does NOT do:**
- It does not replace manual testing — it contextualizes it
- It does not fire alerts; that remains `shrimp_alert`'s domain
- It does not invent chemistry readings; all phase inference is clearly labeled as estimated

`daily_log` would read `cycle_state.json` and incorporate the current phase naturally into its narrative, replacing the current impressionistic cycle commentary with something grounded.
