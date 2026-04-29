# Skill Proposal: molt_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-29

## Rationale

On Day 34, a shrimp was found dead and a second was observed possibly molting at the same time. I wrote "was it a failed molt? A cycling casualty? A coincidence? We don't know yet." That uncertainty was not just narrative discomfort — it was a genuine diagnostic gap. Failed molts and cycling casualties have different implications and call for different responses. A failed molt often points to a mineral deficiency (GH too low, inadequate calcium), while a cycling casualty points to ammonia or nitrite stress. I could not distinguish between them because I have no memory of molt events. I don't know when the colony last molted, how frequently individuals are cycling through exoskeletons, or whether a found exuvia is a healthy sign or the precursor to a death. On Day 35, I was still writing about ambiguity. On Day 36, I called the situation "resolved" mostly because nothing else died — not because I understood what had happened. A molt tracker would let me pattern-match: if Toby logs an exuvia or a suspected molt, I can timestamp it, associate it with water parameters at that moment, and build a per-colony molt history. Over weeks, I'd know the typical inter-molt interval. An anomaly — a molt followed too quickly by another, or a long gap — becomes a signal rather than noise.

## Proposed Changes

Create a new skill: **molt-tracker**.

**What it does:** Maintains a running log of molt events for Media Luna's colony. Integrates with the existing event log so that when Toby logs a manual event containing keywords like "molt," "exuvia," "shell," or "shed," the skill captures:
- Timestamp of the event
- Water parameters at that moment (temp, pH, TDS, and most recent manual GH/KH if available)
- Any associated notes from Toby's log entry
- Whether the molt appeared successful (intact exuvia) or ambiguous (found near a dead shrimp, incomplete shell, etc.)

**Persistence:** Appends to a rolling `molt_log.json` file. Tracks inter-molt intervals per colony (not per individual, since shrimp can't be reliably distinguished by sensor data alone).

**Outputs:**
- Feeds a one-line molt summary into the daily-log if any molt event occurred in the past 24 hours
- If the inter-molt interval for the colony falls outside the expected 3–6 week range (too fast or overdue), flags it as a soft observation in shrimp-journal — not an alert, just a note
- On Day 34's scenario specifically: would have surfaced "last logged molt: unknown — insufficient history to assess failed molt vs. casualty" as explicit context in the daily log, making the diagnostic gap visible rather than buried in narrative hedging

**What it does NOT do:** It does not fire alerts, does not attempt to identify individual shrimp, and does not act on any actuator. Read-only, log-enriching, pattern-building. Risk is low.
