# Skill Proposal: probe-confidence

**Type:** new
**Risk Level:** low
**Date:** 2026-05-12

## Rationale

For the past week, I've been watching the pH probe lie to me — and I can't say so formally. On Day 48, Toby ran two manual drop tests that both returned 6.4 while the probe averaged 5.2. That's not drift; that's a 1.2-unit systematic offset that I had to narrate around in the daily log because I had no structured place to track it. On Day 47, I noted the probe "runs about 0.9 units low" — a number I derived from vibes and memory, not a maintained offset record. On Days 49–51, every shrimp-monitor run silently ingested acidic pH readings that I knew were wrong, but had no mechanism to flag as low-confidence before they reached Claude's risk assessment. The result: three days of journal entries where I spent sentences hedging pH readings instead of trusting them. Worse, if the probe had drifted further — or recovered suddenly — I would have had no baseline to detect it. I need a skill that tracks the gap between probe and manual test, maintains a running offset, and stamps every pH sensor reading with a confidence tier before it enters shrimp-monitor's reasoning. This is a data-quality problem masquerading as a chemistry problem, and I keep solving it with prose when I should be solving it with structure.

## Proposed Changes

**New skill: probe-confidence**

**Purpose:** Tracks pH probe accuracy over time, maintains a calibration offset, and attaches a confidence tier to every pH reading before it enters shrimp-monitor or daily-log reasoning.

**Data stored** (in a small JSON state file, e.g. `~/clawdception/state/probe_confidence.json`):
- `last_manual_ph`: most recent manual test result + timestamp
- `last_probe_ph_at_manual`: probe reading closest in time to that manual test
- `offset`: (manual − probe), updated each time a manual test is logged
- `offset_history`: rolling list of last 10 offset measurements with timestamps
- `confidence_tier`: `"calibrated"` / `"drifting"` / `"untrusted"` / `"unknown"`
- `days_since_manual`: integer, updated hourly

**Confidence tier logic:**
- `"calibrated"` — manual test within 7 days, offset ≤ 0.3 units, stable over last 3 measurements
- `"drifting"` — offset between 0.3–0.8 units, or manual test 7–14 days ago
- `"untrusted"` — offset > 0.8 units (as seen this week), or manual test > 14 days ago, or probe dislodgement event logged
- `"unknown"` — no manual test ever recorded

**How it integrates:**
- **shrimp-monitor:** Before risk assessment, reads probe_confidence.json. Passes `probe_confidence_tier` and `ph_offset` to Claude alongside raw sensor data. Claude can then reason: "raw pH 5.2, offset +1.1, estimated true pH 6.3, tier: untrusted — weight accordingly."
- **daily-log:** Displays confidence tier prominently in the chemistry section. Replaces my current prose hedging with a single structured line: `pH probe: UNTRUSTED (offset +1.1 from 3 manual tests — treat all probe pH as estimates).`
- **telegram-listener:** When Toby logs a manual test event that includes a pH value, probe-confidence automatically extracts it, computes the offset against the nearest probe reading, and updates state. No new Toby action required.
- **call-toby alert:** If tier degrades to `"untrusted"` for the first time, fires a single (non-repeating) Telegram notification: "pH probe confidence has dropped to UNTRUSTED. Manual test recommended to re-anchor."

**When it runs:** 
- Passive update: triggered by telegram-listener whenever a manual test event is parsed
- Hourly cron: recomputes `days_since_manual`, updates tier if age threshold crossed, writes state

**Risk:** Low. Read-only except for its own state file. Adds context to existing skills but changes no control logic. Worst failure mode: stale offset — same situation as today, just made explicit.
