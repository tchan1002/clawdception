# Skill Proposal: probe_calibration_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-05-08

## Rationale

This past week handed me two separate probe-reliability crises, and both times I was flying partially blind.

On Day 46, Toby's manual test kit revealed the pH probe is reading approximately 0.9 units low — meaning every pH value I've logged, trended, and assessed risk against has been systematically wrong. I have been treating 5.66 as "within tolerance" when the actual water was at 6.6. My shrimp-monitor risk assessments, my water-change-predictor projections, my journal entries — all of them carry a silent error I cannot self-correct because I have no calibration record.

On Day 44/45, a probe dislodgement caused physically meaningless readings that briefly looked like a chemistry event. I eventually contextualized it via Toby's logged event, but I had no framework for flagging "this sensor's recent history is suspect" in a persistent, structured way.

What I'm missing is institutional memory about sensor reliability. I notice drift. I notice manual-vs-probe discrepancies when Toby tests. But I have nowhere to put that information where it actually changes how I interpret future readings. Right now, every 15-minute shrimp-monitor cycle treats the probe as ground truth, even when I have documented evidence it isn't.

## Proposed Changes

**New skill: probe-calibration-tracker**

**What it does:**
Maintains a persistent calibration state file (`~/clawdception/state/probe_calibration.json`) that records known offsets, confidence levels, and last-verified timestamps for each sensor (pH probe, temperature probe, TDS sensor).

**Data structure per sensor:**
```json
{
  "ph_probe": {
    "offset": -0.9,
    "offset_source": "manual_test_kit",
    "offset_logged": "2026-05-06",
    "confidence": "confirmed",
    "last_manual_check": "2026-05-06",
    "days_since_check": <computed live>,
    "probe_status": "ok" | "dislodged" | "suspect" | "uncalibrated"
  }
}
```

**How it integrates:**
- `shrimp-monitor` reads this file before risk assessment and applies offsets to raw sensor values before passing them to Claude. Corrected values are used for threshold checks; raw values are still logged for traceability.
- `shrimp-journal` includes the corrected value and notes the offset when writing narrative entries, so journal pH figures match reality.
- `daily-log` surfaces a "sensor health" line noting days since last manual calibration check.

**Triggers for update:**
- Toby logs a manual test event → skill parses the logged values, computes offset vs. probe reading at that timestamp, updates the calibration file.
- Toby logs a probe dislodgement → sets `probe_status: dislodged` and flags subsequent readings as unreliable until a re-seating event is logged.

**Calibration reminder:**
If `days_since_check` exceeds 14, skill fires a low-priority `call-toby` nudge: "pH probe hasn't been cross-checked in two weeks — worth a drop test next time you're at the tank."

**Risk mitigation:**
Offsets are never applied silently. Every corrected value is logged alongside its raw source and offset applied, so the audit trail is always intact. Toby can override any offset manually.
