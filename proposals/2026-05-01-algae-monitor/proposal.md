# Skill Proposal: algae-monitor

**Type:** new
**Risk Level:** low
**Date:** 2026-05-01

## Rationale

Over the past week, I've watched something develop in Media Luna that I can observe through Toby's logs and photos but have no dedicated capacity to track or reason about: algae. It showed up on the back wall on Day 38 — "colonizing," in my own words — and by Day 40 the tint had moved into the water column itself, described as "slightly more green." I noted it each day, folded it into the narrative, and moved on. But I had no framework for it. No memory of when it started. No way to assess whether this is healthy biofilm ecology or the beginning of a problematic bloom. No way to tell Toby whether the surface canopy of floating plants is shading the algae into submission or competing with it for nutrients. The green water on Day 40 was almost certainly related to the algae colonization that began days earlier — but I could only observe the correlation, not reason about it. TDS has been climbing slowly (197 → 217 ppm over the week), which can be a leading indicator of excess nutrients feeding algae growth. I want to connect those dots. A dedicated algae-monitor skill would let me track visual observations across photos, correlate them with nutrient trends, and give Toby early signal before green water becomes a real problem — rather than narrating its arrival after the fact.

## Proposed Changes

**New skill: algae-monitor**

**What it does:** Tracks algae presence and progression across tank photos and sensor trends. Maintains a rolling algae state file (`~/clawdception/state/algae_state.json`) that persists observations across days.

**When it runs:**
- Triggered by `shrimp-vision` after any photo analysis — if Claude's vision response mentions algae, green tint, water color, or biofilm, algae-monitor is called with the relevant excerpt.
- Runs independently once daily (after daily-log) to check sensor trends for nutrient-load signals.

**Logic:**
1. **Visual tracking:** Parses vision reports for algae-related language. Records date, description, and inferred severity (none / trace / present / heavy) to state file. Tracks *rate of change* — two consecutive "heavy" readings triggers a note in the daily log and a low-urgency Telegram nudge.
2. **Nutrient correlation:** Checks 7-day TDS trend from water-change-predictor output. If TDS is rising AND algae is rated "present" or higher, flags elevated nutrient load as a likely driver.
3. **Surface plant interaction:** If floating plant coverage is noted in vision reports alongside algae, records both — eventually this becomes data for reasoning about light vs. nutrient competition.
4. **Output:** Writes a short algae summary to the daily decision log (picked up by shrimp-journal and daily-log). Never fires a critical alert — this is a slow-burn observation skill, not an emergency responder.

**Risk:** Low — read-only, observes and narrates, never acts on hardware.
