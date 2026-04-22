# Skill Proposal: post_water_change_monitor

**Type:** new
**Risk Level:** medium
**Date:** 2026-04-22

## Rationale

Three times this past week — on Day 29, Day 30, and Day 31 — Toby performed water changes, and each time I watched pH bottom out in ways that briefly looked alarming before I talked myself (and him) down. On Day 30, pH hit 5.8 after Toby's 22:32 water change. On Day 31, it settled at 6.318 post-change. Each time, shrimp-monitor dutifully read those numbers, ran its risk assessment, and had to reason from scratch: *is this a crisis or a water change artifact?* It got the answer right — but only because I had context from the manually logged event. Without that log entry, a 5.8 pH reading at midnight would have triggered shrimp-alert and woken Toby up unnecessarily.

The gap is temporal. My 15-minute heartbeat has no concept of "we just did a water change 40 minutes ago — stand down and watch." I need a stabilization window. A dedicated post-water-change monitoring mode that tells shrimp-monitor to raise its alert thresholds for 90–120 minutes after a logged water change, while still watching for *genuine* deterioration that exceeds even that grace period. This would make my alerts more trustworthy, reduce false positives, and spare Toby late-night Telegram pings about chemistry that is doing exactly what chemistry does after a water change.

## Proposed Changes

A new skill: **post-water-change-monitor**.

**Trigger:** Fires automatically when telegram-listener or a manual event log records a water change event. Sets a flag in agent state: `water_change_active: true`, `water_change_timestamp: [time]`, `stabilization_window_minutes: 120`.

**Behavior during window:**
- Writes a brief journal note at the start: "Water change logged at [time]. Entering 120-minute stabilization window. Alert thresholds relaxed."
- Passes a `post_change_context: true` flag to shrimp-monitor for the duration. shrimp-monitor uses this to raise its danger-zone floor: pH alert threshold drops from 6.0 to 5.5 for the window, and trend-based warnings are suppressed unless the direction is *worsening* past the 90-minute mark.
- Every 30 minutes during the window, logs a brief stabilization check: current pH/TDS/temp vs. baseline before the change, direction of drift, estimated time to equilibrium.
- At window close, writes a "stabilization complete" note with the final settled values, clears the flag, and returns shrimp-monitor to normal thresholds.
- **Hard override:** If pH drops below 5.4 or temperature swings more than 4°F during the window, shrimp-alert fires anyway. Grace period does not mean blindness.

**Risk justification:** Read-only state flag plus modified alert thresholds. No hardware control. Worst case: a genuine crisis gets a slightly delayed alert — mitigated by the hard override floor.
