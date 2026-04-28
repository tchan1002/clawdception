# Skill Proposal: molt-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-28

## Rationale

Day 34 — "The First Hard Night" — is the clearest argument for this skill. A shrimp was found dead under the filter bar. Around the same time, a second shrimp was observed possibly molting. The daily log acknowledges the ambiguity plainly: "was it a failed molt? A cycling casualty? A coincidence? We don't know yet." We still don't. And that uncertainty wasn't just narrative texture — it was a diagnostic gap. Failed molts in Neocaridina are often linked to low mineral content (insufficient GH/KH), but I had no molt history to reason from. I couldn't say whether this was a first molt, a regular one, or an outlier. I had no baseline.

Molting is one of the most consequential recurring events in a shrimp colony's life. It's a vulnerability window, a GH/KH signal, a population health indicator, and — when it fails — a cause of death. Right now, when Toby logs a molt observation, it disappears into the event stream. No accumulation. No pattern detection. No flag when the interval looks wrong or a molt seems incomplete. I'm watching a tank full of animals that molt regularly, and I have no memory of their molts. That's a real gap, and Day 34 proved it.

## Proposed Changes

**New skill: molt-tracker**

**What it does:** Maintains a persistent molt log and reasons about molt health over time. Operates in two modes:

**1. Passive intake:** Listens for any logged event containing molt-related keywords ("molt," "exoskeleton," "shell," "shed," "white casing"). When detected — whether from Toby's manual logs, shrimp-vision photo analysis, or journal entries — it extracts and records: timestamp, whether the molt appeared successful or incomplete/failed, and any associated water parameters at time of molt.

**2. Weekly analysis (runs after skill-writer, Sunday mornings):** Reads the accumulated molt log and asks Claude to assess:
- Average molt interval per identifiable individual (if Toby has named/described shrimp)
- Whether recent TDS/GH trends correlate with molt timing or failures
- Whether any molt was flagged as incomplete or followed by a death event within 48 hours
- A plain-language molt health summary appended to the weekly state file

**Alerts:** If two or more failed/incomplete molts are logged within a 7-day window, fires a call-toby notification flagging possible mineral deficiency with current TDS for context.

**Risk rationale:** Read-mostly. Writes only to its own log file and the weekly state. No actuator access. The only active output is a Telegram alert under a specific multi-failure condition.

**Files touched:** `~/clawdception/molt_log.json`, `~/clawdception/state/molt_summary.md`
