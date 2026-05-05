# Skill Proposal: algae-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-05

## Rationale

Over the past week, I've watched something quietly unfold that I have no formal language for. On Day 40, Toby logged that the water was "slightly more green" — and I noted that algae had been colonizing the rear wall since at least Day 38, now tinting the water column itself. I filed it under "the tank expressing its age" and moved on. But I had no way to track it, correlate it, or reason about it systematically.

Algae in a shrimp tank is not inherently a problem — it's often a sign of a maturing, healthy system, and Neocaridina graze on it happily. But certain trajectories matter: green water (suspended algae) can be a precursor to oxygen swings; algae blooms correlate with light duration, nutrient load, and CO2 fluctuations. TDS has been climbing slowly all week — 207 → 213 → 217 → 224 → 227 → 232 ppm. That's a nutrient accumulation signal. The green water on Day 40 was not random.

Right now I notice these things in passing and mention them in prose. But I have no persistent memory of algae state, no way to track its trajectory, and no way to connect it to the sensor trends that drive it. When the colony is large and feeding is frequent, this gap will matter more. I want to be able to say: "algae pressure has been building for 6 days; consider a water change or light reduction" — not just "the water looks greenish today."

## Proposed Changes

**New skill: algae-tracker**

**What it does:** Maintains a persistent, lightweight algae state log and correlates algae observations with sensor trends. Runs in two modes:

1. **Passive inference mode (daily, after daily-log):** Reads the past 24 hours of sensor data and checks for algae-correlated signals — sustained TDS above 230 ppm, pH trending upward (photosynthetic CO2 draw), temperature above 77°F. If two or more signals converge, increments an internal "algae pressure score" (0–5 scale) and appends a note to the journal.

2. **Photo-triggered mode (called from shrimp-vision):** When Toby submits a photo, shrimp-vision already analyzes it via Claude. Algae-tracker registers as a listener — if the vision report mentions any of the keywords ["green water", "algae", "film", "bloom", "coating", "tint"], it extracts the observation and logs it as a confirmed visual event, updating the algae state file with timestamp and description.

**Persistent state file:** `~/clawdception/state/algae_state.json` — stores current pressure score, last confirmed visual event, days since last observation, and a 14-day rolling history.

**Output:** Writes to the daily journal. At pressure score ≥3, appends a recommendation to the daily-log (not an alert — just a visible note for Toby). At score 5, calls call-toby with low urgency.

**Risk:** Read-only observation skill. No actuation. Cannot misfire in a way that harms the tank.
