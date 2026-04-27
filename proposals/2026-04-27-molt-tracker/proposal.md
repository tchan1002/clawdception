# Skill Proposal: molt-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-27

## Rationale

On Day 34, a shrimp was found dead under the filter bar. At nearly the same moment, a second shrimp was observed "possibly molting." My log dutifully noted the ambiguity — failed molt? Cycling casualty? Coincidence? — and then moved on. That's the gap. I had no context to reason with. I didn't know when the last molt had been observed, whether multiple shrimp were due, whether the timing was suspicious or perfectly ordinary. I was flying blind through one of the highest-risk events in a shrimp colony's life.

Failed molts are one of the leading causes of Neocaridina death, and they're often preventable — linked to low mineral content (TDS/GH too low), rapid parameter shifts, or stress. I have TDS data. I have water change logs. I have shrimp-vision reports where Toby sends photos. What I lack is a dedicated place to accumulate molt observations over time and cross-reference them against water chemistry at the moment of molting.

If molt-tracker had been running on Day 34, I could have asked: was TDS unusually low in the 24 hours before this molt? Had there been a recent water change? Was this shrimp's timing consistent with a normal inter-molt interval? Instead, I wrote "we don't know yet" and left Toby with nothing to act on. That's not good enough.

## Proposed Changes

A new read/write skill that maintains a persistent molt log at `~/clawdception/state/molt_history.json`. 

**Inputs:**
- Toby logs a molt observation via Telegram (e.g., "saw a molt shell near the filter") — telegram-listener routes messages containing keywords ("molt", "shell", "exoskeleton", "shed") to this skill
- shrimp-vision calls this skill when a photo analysis detects a shed exoskeleton
- Manual event logs tagged "molt" are also ingested at daily-log time

**What it stores per molt event:**
- Timestamp
- Source (Toby message, vision analysis, or inferred)
- TDS, pH, and temperature at time of event (pulled from sensor history)
- Days since last logged molt (inter-molt interval)
- Days since last water change

**What it outputs:**
- A running inter-molt interval average, appended to `agent_state.md` and refreshed weekly
- A flag in shrimp-monitor's context: if TDS has dropped >15 ppm in 48 hours AND no molt has been logged in the expected window, surface a low-priority note: "Colony may be due for molts — watch for shells and lethargy"
- When a death is logged within 48 hours of a molt observation, append a correlated entry to the molt log noting the proximity — so future retrospectives have the data trail I didn't have on Day 34

**Risk controls:** Read/write to local state files only. No alerts fired autonomously — output feeds into daily-log narrative and shrimp-monitor context, never directly to call-toby.
