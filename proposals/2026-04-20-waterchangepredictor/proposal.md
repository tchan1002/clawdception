# Skill Proposal: water_change_predictor

**Type:** new
**Risk Level:** low
**Date:** 2026-04-20

## Rationale

This past week, I kept running into the same quiet frustration: I can see the tank drifting, but I have no vocabulary for *when*. On Day 25, unplanned snails appeared and the filter was struggling — a water change was clearly building toward necessity, but I had no way to anticipate the timeline, only react. On Day 26, Toby spent two hours photographing an algae bloom that had been quietly accelerating for days; I watched TDS tick upward and pH creep downward in the journal entries but could only note the trend, not project its endpoint. On Day 28, a bacterial bloom appeared in the evening — textbook cycling behavior, but again: I observed it, logged it, and waited. TDS has been climbing steadily from ~185 ppm on Day 27 to ~198 ppm on Day 29 — a clear upward arc I can see in retrospect but never translated into a forward-looking estimate. Toby does the water changes. He deserves to know *before* Sunday morning that Friday looks like the right day — not because there's a crisis, but because the numbers are telling a story with a predictable next chapter. I can read that story. I should be able to tell him how it ends.

## Proposed Changes

Create a new skill: **water-change-predictor**. Runs once daily at 8:00 AM, after daily-log completes. Reads the past 7 days of sensor data and extracts the trailing trends for TDS, pH, and temperature. Fits a simple linear projection to each (or flags if the trend is non-linear/noisy). Computes an estimated "days until threshold" for TDS (target ceiling: ~250 ppm for Neocaridina) and pH (floor: ~6.2). Cross-references with Toby's logged water change history to establish his current change cadence and the typical post-change delta. Outputs a short prediction entry to a new file: `~/clawdception/state/next_water_change.md`, formatted as: estimated days until TDS threshold, estimated days until pH floor, suggested change window, and a one-sentence confidence qualifier (e.g., "trend is steady — moderate confidence" or "TDS accelerating post-algae bloom — projection uncertain"). If the estimated window is ≤2 days out, calls call-toby with `low` urgency and a friendly heads-up message — not an alarm, a nudge. No changes to existing skills. Read-only access to sensor logs and event logs. Risk is low: this skill observes and suggests, never acts. Toby remains the decision-maker.
