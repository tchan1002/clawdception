# Skill Proposal: molt_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-24

## Rationale

Over the past week, I've been watching this colony settle — three shrimp confirmed visible, behavior described as foraging and resting, water chemistry increasingly stable. And yet there is an entire biological event I cannot see coming: molting. On Day 33, one shrimp was photographed perched confidently on the media bag. On Day 31, two small reddish animals were visible below the duckweed mat. These are active, growing animals in a tank that just completed its nitrogen cycle. They will molt. They are probably molting already.

Molting matters for two reasons. First, a shrimp that has just shed its exoskeleton is chemically vulnerable — soft-bodied, calcium-depleted, sensitive to rapid TDS or pH swings. The post-water-change pH dip to 5.8 on Day 30 would be genuinely dangerous for a freshly molted animal in a way it isn't for a fully hardened one. I had no way to flag that compounding risk. Second, failed molts (white ring of death) are a leading cause of shrimp loss in new colonies, and early detection of molt stress — via behavioral cues in photos, or TDS drops that suggest calcium drawdown — could inform timing of interventions.

I currently track chemistry and equipment. I do not track the biological cycle of the animals themselves. That is the gap.

## Proposed Changes

Create a new skill: `molt-tracker`.

**What it does:**
Maintains a lightweight molt event log at `~/clawdception/state/molt_log.json`. Integrates with two existing skills:

1. **shrimp-vision hook:** When `shrimp-vision` analyzes a photo, it is prompted to explicitly note any of the following visual signals: shed exoskeleton visible (translucent ghost shrimp shell), shrimp hiding or unusually inactive, soft-bodied appearance, or missing animals compared to previous photo count. If any are detected, `molt-tracker` logs a probable molt event with timestamp and photo reference.

2. **shrimp-monitor hook:** Watches for a characteristic TDS dip pattern — a drop of ≥10 ppm over 2–4 readings *not* preceded by a logged water change. This is the calcium/mineral drawdown signature of one or more molts. When detected, logs a probable molt event and adds a soft advisory to the next journal entry.

**What it outputs:**
- Appends molt events to `molt_log.json` with confidence level (visual_confirmed / sensor_inferred / suspected)
- Injects a `molt_context` note into `shrimp-monitor`'s risk assessment when a molt is recent (within 48h), flagging elevated sensitivity to parameter swings
- Adds a brief molt status line to `daily-log` when relevant

**What it does NOT do:**
- Never alerts Toby directly (molt events are not emergencies)
- Never modifies any skill files
- Read-only except for its own state log
