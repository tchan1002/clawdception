# Skill Proposal: nitrate_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-30

## Rationale

For five consecutive days this week — Days 35 through 39 — my logs noted nitrate at 80 ppm and called it "high but expected" or "rising but stable." Each entry treated 80 ppm as a fresh observation rather than a persistent, accumulating condition. I had no memory of how many days we'd been sitting at this ceiling, no rate-of-change estimate, and no projected date by which a water change would become non-optional. On Day 35 ("Rest in Power"), I wrote that nitrate was "the fingerprint of a maturing biological filter doing real work" — which is true — but I offered Toby nothing actionable. On Day 39, the journal noted it again without escalation. Neocaridina tolerate nitrate up to roughly 20 ppm in a mature tank; the cycling context gives us more latitude, but 80 ppm for 5+ days is a trend I should be naming clearly, not absorbing into boilerplate. The water-change-predictor skill tracks TDS and pH drift toward thresholds. Nitrate — arguably the more biologically urgent number at this stage — has no equivalent tracker. That is the gap. Manual test events log nitrate as a point reading; nothing connects the dots across days or tells Toby "this is the fifth day above 80 ppm, a water change in the next 48 hours is advisable."

## Proposed Changes

**New skill: nitrate-tracker**

**What it does:** Runs daily after daily-log. Reads all manual test events from the past 14 days that include a nitrate reading. Computes: (1) current nitrate, (2) days since last reading below a "comfortable" threshold (20 ppm post-cycle, 40 ppm during active cycling), (3) a simple linear trend projecting days until the next water change becomes necessary at 20 ppm/day accumulation. Writes a short structured projection block — similar to water-change-predictor output — to a file like `~/clawdception/state/nitrate_state.json`.

**Integration:** daily-log reads this file and incorporates nitrate context into its narrative when nitrate has been elevated for 3+ consecutive readings. shrimp-journal reads it for the "days at ceiling" count. If nitrate exceeds 80 ppm for 5+ consecutive days without a water change event logged, skill fires call-toby with `medium` urgency: *"Nitrate has been ≥80 ppm for 5 days. Water change worth considering soon."*

**Thresholds:**
- Cycling phase (ammonia/nitrite still detected): warn at 80 ppm / 5 days
- Post-cycle: warn at 40 ppm / 3 days, alert at 60 ppm / 2 days

**Risk:** Read-only observation and single medium-urgency Telegram nudge. No actuation. Low risk of false alarm since it requires multiple consecutive manual test events to trigger.
