# Skill Proposal: duckweed-monitor

**Type:** new
**Risk Level:** low
**Date:** 2026-04-23

## Rationale

Over the past week, I've watched the duckweed become a recurring character in this tank's story — and I've had no structured way to reason about it. On Day 31, Toby's photo showed "nearly continuous green coverage." On Day 32, I described "hundreds of bright lime-green fronds" forming a near-solid mat, with only small open windows and a turbulence zone near the filter outflow maintaining any surface break. I noted this in narrative prose, but I had no framework to translate what I was seeing into water chemistry implications.

This matters for shrimp welfare. Dense floating plant coverage reduces surface gas exchange — CO₂ off-gassing slows, which can suppress pH in an already soft, low-pH tank like Media Luna. On Day 20, after a water change, pH briefly hit 5.8. I attributed that to post-change equilibration, and I still think that's right — but I have no way to know whether a near-sealed duckweed mat is compounding these dips by trapping CO₂. I'm also blind to light penetration, which affects plant health below the surface.

This is a pattern I can observe (via shrimp-vision photo analysis) but cannot yet reason about systematically. I keep noting the duckweed and moving on. I should be correlating surface coverage density with pH trend behavior and flagging when coverage looks likely to impair gas exchange.

## Proposed Changes

**New skill: duckweed-monitor**

**Trigger:** Runs after any shrimp-vision photo analysis that includes a top-down or partial surface view. Passive — no new camera requirements. Works entirely from photos Toby already submits.

**What it does:**

1. **Surface coverage estimation.** When shrimp-vision processes a photo, duckweed-monitor reads the vision report and extracts any surface coverage description. Using Claude, it estimates coverage as a rough percentage band (e.g., <25%, 25–50%, 50–75%, >75%) and logs this to a lightweight state file: `tank_state/surface_coverage.json`, with timestamp and photo source.

2. **pH correlation check.** After logging coverage, it queries the last 48 hours of pH sensor readings and checks whether pH trend is flat, declining, or recovering. If coverage is estimated >75% AND pH shows a declining trend (not explained by a recent water change in the event log), it writes a flagged journal entry noting the potential gas-exchange concern.

3. **Toby nudge (non-urgent).** If the >75% + declining pH condition persists across two consecutive photo assessments with no water change in between, it calls call-toby at `info` urgency — not an alert, just a nudge: *"Surface coverage is dense and pH is drifting down. Worth thinning the mat?"*

4. **Coverage history in daily-log.** Passes latest coverage estimate to daily-log context so I can reference it without re-deriving it from prose each morning.

**Risk rationale:** Read-only except for the Toby nudge, which uses the lowest urgency tier. Cannot misfire into a false alarm since it requires both visual confirmation and a sustained sensor trend. Low blast radius.
