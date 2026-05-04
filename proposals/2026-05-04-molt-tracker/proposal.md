# Skill Proposal: molt-tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-04

## Rationale

Over the past week, Media Luna became a real colony. On Day 41, Toby logged five new shrimp joining the one resident — and buried in that entry is a detail that has stayed with me: "one difficult molt." I have no record of what made it difficult, whether the shrimp recovered, or whether any exuvia were found afterward. I noted it in the daily log with care, and then I let it disappear into the narrative. That's the gap.

Molting is the single most dangerous recurring event in a shrimp's life. Failed molts kill. "Difficult molt" is exactly the kind of signal I should be tracking — not just narrating. With a colony now established and TDS climbing steadily from 203 ppm on Day 37 to 232 ppm on Day 43, mineral balance is becoming relevant. Hardness affects molting success. A molt-tracking log would let me correlate molt events (logged by Toby or flagged by shrimp-vision) with water chemistry at the time — giving me, over weeks, a real picture of whether this tank's mineral profile is supporting clean molts or creating friction.

Right now I can describe a difficult molt beautifully. I cannot learn from it.

## Proposed Changes

A new lightweight skill — molt-tracker — that maintains a structured molt event log at `~/clawdception/state/molt_log.json`. 

**Event ingestion (three sources):**
1. **Manual log:** When Toby logs a Telegram message containing keywords ("molt," "exuvia," "shell," "shed"), telegram-listener flags it and molt-tracker appends an event with timestamp, water params at time of event, and a "source: manual" tag.
2. **shrimp-vision integration:** When shrimp-vision analyzes a photo and detects an exuvia or a shrimp in a compromised posture, it can write a "suspected molt" event to the same log.
3. **Direct Telegram command:** Toby can text "molt [outcome]" (e.g., "molt clean", "molt difficult", "molt death") to log an event immediately.

**Each event record:**
```json
{
  "timestamp": "ISO8601",
  "outcome": "clean | difficult | death | unknown",
  "pH_at_event": float,
  "TDS_at_event": int,
  "temp_at_event": float,
  "source": "manual | vision | command",
  "notes": "raw text if any"
}
```

**Weekly summary (runs inside skill-writer's review window):** If ≥2 molt events exist in the log, generate a brief correlation note — does TDS above X correlate with difficult molts? — and surface it in the next daily-log.

**No alerts, no interventions.** This skill only observes and records. Risk is read-only.
