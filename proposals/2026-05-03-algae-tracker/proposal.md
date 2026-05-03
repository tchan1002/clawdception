# Skill Proposal: algae-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-03

## Rationale

Over the past week, I've watched something green and patient take hold of Media Luna — and I've had no way to reason about it systematically. Day 38 logs noted algae colonizing the back wall and biofilm on the sponge filters. Day 40, Toby described the water as "slightly more green," a tint showing up in the water column itself. Day 39, the floating plant canopy had grown dense enough to dominate the tank's entire surface. Each of these was logged in isolation — a detail in a daily narrative, a footnote in a journal entry. But they are the same story told in three chapters: the tank's biology is maturing in a particular direction, and I am not tracking it as a coherent trend.

This matters for shrimp welfare. Surface coverage affects gas exchange and light penetration. Green water signals a shift in nutrient balance. Biofilm accumulation on equipment can precede flow restriction. Right now, these signals arrive as one-off observations from photos and manual events, and they dissolve into the journal without accumulating into anything I can reason against. By Day 42, when I noted the colony had settled and chemistry was stable, I had no structured way to say: "stable chemistry, yes — but the biological substrate is drifting." That's a gap I keep bumping into.

## Proposed Changes

A new read-only skill called **algae-tracker** that maintains a lightweight longitudinal record of biological surface conditions in Media Luna.

**Data sources:**
- `shrimp-vision` outputs (photo analyses mentioning algae, biofilm, surface coverage, water tint/turbidity)
- Manual events logged by Toby (descriptions like "slightly more green," "back wall colonized," "biofilm on filter")
- Sensor-derivable proxies: rising TDS without a corresponding conductivity event can suggest organic accumulation; pH drift toward lower values during lights-on hours can suggest photosynthetic activity

**What it tracks (written to a rolling state file `algae_state.md`):**
- Surface plant coverage: estimated low / partial / dense (derived from vision reports)
- Glass algae: none / present / spreading
- Water tint: clear / hazy / green-tinted
- Filter biofilm: none / light / notable
- Last updated timestamp and source (vision, manual event, or inferred)

**When it runs:** After every `shrimp-vision` call and after any manual event is logged. Also runs daily alongside daily-log to update the state file and append a one-line trend note.

**Output:** The state file is read by `daily-log` to include a "Biological Texture" sidebar — a short paragraph contextualizing chemistry stability against what the living surfaces are doing. No alerts, no actuation. Pure observational memory.

**Risk:** Low. Read-only. Writes to a new state file only. No changes to alerting logic.
