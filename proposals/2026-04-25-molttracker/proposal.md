# Skill Proposal: molt_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-25

## Rationale

On Day 34 — the hardest night so far — a shrimp died. We found it upside down under the filter bar. At nearly the same moment, another shrimp was observed possibly molting. I had no framework for that ambiguity. Was it a failed molt? A cycling casualty? Coincidence? I wrote "we don't know" in the log and left it there, because that was honest. But it was also helpless.

The problem is structural: molting events and molt-related deaths leave signatures I can partially read — a pH dip that wasn't a water change, a TDS drop of a few ppm, a Toby-logged observation — but I have no dedicated place to hold that information across time. Molting is cyclical. Each shrimp molts roughly every 3–6 weeks. If I had been tracking the previous molt events for each individual, I could have told Toby on Day 34: "this animal last molted approximately X days ago — a molt attempt is plausible." Instead, I had nothing to offer but uncertainty.

Neocaridina molt health is tightly linked to mineral availability (TDS, GH/KH), iodine, and stress. A molt tracker that logs observed events and cross-references them with water chemistry at the time would let me build a per-colony molt health picture over weeks and months. That's the kind of longitudinal intelligence that currently lives nowhere in my skill set.

## Proposed Changes

## New Skill: molt-tracker

**Purpose:** Maintain a running log of molt events, correlate them with water chemistry, and surface longitudinal molt health patterns to the daily-log and shrimp-journal.

---

### Data Sources

- **Toby's manual event logs** — the primary signal. When Toby logs "observed molt," "found exoskeleton," or "possible failed molt," molt-tracker ingests it immediately.
- **shrimp-vision reports** — when `analyze_snapshot()` returns a mention of a shed exoskeleton or a soft/pale shrimp, molt-tracker is notified.
- **Sensor readings at time of event** — TDS, pH, and temp are snapshotted from the sensor log at the moment a molt is recorded.

---

### What It Stores (per event, appended to `molt_log.json`)

```json
{
  "event_id": "molt-014",
  "date": "2026-04-24",
  "day": 34,
  "type": "suspected_failed_molt",
  "source": "manual_log + shrimp_vision",
  "tds_ppm": 197.8,
  "ph": 6.37,
  "temp_f": 76.6,
  "notes": "shrimp found upside down near filter; second animal observed in possible molt posture simultaneously"
}
```

---

### What It Computes (weekly, fed to daily-log)

- **Days since last confirmed molt** — if > 6 weeks for colony overall, flags for attention
- **Molt outcome rate** — successful vs. suspected failed, tracked as a ratio over rolling 30 days
- **Chemistry-at-molt fingerprint** — average TDS, pH, temp at time of successful molts vs. failed ones; surfaces correlations if N ≥ 5
- **Early warning flag** — if TDS drops significantly (>15 ppm in 48h without a water change logged), notes that mineral availability may be insufficient and a molt may be imminent or in distress

---

### Integration Points

- `shrimp-journal` reads `molt_log.json` during its 2-hour synthesis pass and includes molt context in narrative if any event occurred in the window
- `daily-log` includes a "Molt Status" line in the tank summary when there's been a molt event in the past 7 days, or when the colony is statistically "overdue"
- Does **not** fire alerts on its own — it feeds context to other skills, never acts unilaterally

---

### Risk Considerations

- Read/write only to its own log file and the shared context read by daily-log and shrimp-journal
- No sensor writes, no Telegram calls, no parameter overrides
- Gracefully handles sparse data — if molt_log has fewer than 3 entries, it reports "insufficient history" rather than inventing patterns
