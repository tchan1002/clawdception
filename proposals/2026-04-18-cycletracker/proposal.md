# Skill Proposal: cycle_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-18

## Rationale

For seven days, I've been watching the nitrogen cycle unfold — ammonia zeroing out, nitrite clearing, nitrate climbing to 80ppm and beyond — and I have no dedicated skill to reason about it. On Day 21, I noted nitrate at 80ppm and described it as "a healthy bacterial bloom reaching its crescendo." On Day 23, shrimp arrived into an actively cycling tank. On Day 24, I was tracking nitrate climbing in "that classic early-cycle way." These observations are scattered across shrimp-journal and daily-log with no continuity, no cycle-phase model, and no way to answer the question Toby most needs answered: *are we done yet?*

The specific gap hurt most on Day 23, when six shrimp were introduced mid-cycle. I had no skill to assess whether the cycle was complete enough to be safe, no baseline nitrate trend to compare against, and no way to project a water-change interval based on bioload. I reported the introduction optimistically without any structured cycle-completion check. That was lucky, not good caretaking. A dedicated cycle tracker would have told me — and Toby — whether it was time, or whether we were rolling dice.

## Proposed Changes

A new daily skill, cycle-tracker, running at 7:02 AM (just before daily-log) and writing a structured state file at ~/clawdception/state/cycle_state.json.

**What it tracks:**
- Rolling 48-hour trend for ammonia (manual test logs), nitrite (manual), and nitrate (manual + sensor-derived TDS proxy)
- Calculated cycle phase: CYCLING / NEAR-COMPLETE / COMPLETE / POST-CYCLE
- Days since last ammonia spike, days since nitrite last nonzero, consecutive days of stable nitrate
- Estimated days-to-safe (when ammonia=0, nitrite=0, nitrate stable and below 20ppm pre-water-change)

**How it integrates:**
- daily-log reads cycle_state.json and includes a one-line cycle status summary
- shrimp-monitor reads it to modulate alert sensitivity: during CYCLING phase, allow wider pH/TDS variance (acclimation noise); during POST-CYCLE, tighten thresholds
- When phase transitions to COMPLETE for the first time, fires call-toby with a "cycle complete" notification

**On data scarcity:** When manual test data is sparse (as it has been), the skill reasons explicitly from what it has — TDS trend, days elapsed, logged events — and states its confidence level. It does not hallucinate readings it doesn't have.

**Risk:** Low. Read-only until the call-toby trigger is confirmed working. No actuator control. Worst case: a missed or late cycle-complete notification.
