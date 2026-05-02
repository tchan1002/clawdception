# Skill Proposal: molt-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-02

## Rationale

This past week exposed a gap I keep running into: I can see the colony, but I can't see through time. On Day 41, five new shrimp arrived and one underwent a "difficult molt" — my log noted it, named it, and then had no further structure for tracking it. What happened to that shrimp after the molt? Did it harden successfully? Did it disappear into the substrate to recover? I don't know, because I have no persistent molt record. I'm also watching TDS and pH trend upward week over week (203 → 207 → 213 → 217 ppm; pH slowly climbing), and I know from shrimp biology that molting is tightly coupled to water chemistry — particularly GH and TDS. When a shrimp molts poorly or fails to molt at all, it's often the first signal that mineral balance is drifting. Right now I can describe a difficult molt in prose and move on. What I can't do is correlate it against water chemistry at the time, flag if molt frequency is declining, or notice that the same individual has struggled twice in two weeks. With a colony that just grew from one to six, molt health is about to matter a lot more. I need somewhere to put that information so it accumulates into signal rather than dissolving into narrative.

## Proposed Changes

A new read/write skill called `molt-tracker` that maintains a persistent molt log at `~/clawdception/state/molt_log.json`. 

**Triggered by:** 
1. Toby logging a manual event containing keywords: "molt," "shed," "exoskeleton," "shell," "exuvia" — telegram-listener routes these to molt-tracker automatically.
2. shrimp-vision, when analyzing a photo, flags visible exuvia or a soft/pale shrimp and calls molt-tracker with the observation.

**What it records per event:**
- Timestamp
- Source (manual log, vision, or inferred)
- Outcome: `successful`, `difficult`, `failed`, `unknown`
- TDS, pH, and temperature at time of event (pulled from latest sensor reading)
- Optional notes (from Toby's log text or vision analysis)

**What it computes weekly (called by skill-writer pass and daily-log):**
- Molt frequency over past 30 days
- Mean water parameters at molt events
- Flag if no molts recorded in 21+ days (potential sign of stalled mineral balance or stress)
- Flag if ≥2 "difficult" or "failed" molts in 14 days

**Output:** Appends a short molt summary block to the daily log when there's something to report. Silent otherwise — no noise if the shrimp are molting cleanly and regularly. Sends a Telegram nudge to Toby if a "difficult" molt is logged and no follow-up observation has been recorded within 48 hours.
