# Skill Proposal: cycle_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-10

## Rationale

For seven days straight, I've been watching this tank sit at the finish line — ammonia zero, nitrite zero, nitrate at 80 ppm — and I have had no vocabulary for it. No skill that says: *you're done, you've been done for four days, here's what that means and here's what comes next.* 

The daily logs from Days 17, 18, and 19 all circle the same observation: "this is what a finished cycle looks like." I wrote that. Three times. But I couldn't *act* on it — I couldn't surface a recommendation, couldn't track the streak, couldn't tell Toby that he'd now had 72+ consecutive hours of clean readings and that the decision window for introducing shrimp was open.

Then there's the other direction: Day 15's plateau. Nitrite stuck at 2.0 ppm, ammonia at 0.25 ppm, pH sliding toward 6.4. I flagged it as concerning in the journal, but I had no structured sense of *how long* it had been stuck, or whether the plateau duration itself was a signal worth escalating. I was reacting to each snapshot without memory of the shape.

A cycle tracker would give me — and Toby — a continuous read on where we are in the biological narrative, not just the chemistry snapshot. It's the difference between reading a single sentence and knowing the chapter.

## Proposed Changes

**New skill: cycle-tracker**

Runs once daily at 7:02 AM (just before daily-log at 7:00 AM writes its entry, so the tracker's output feeds into the log).

**What it does:**

1. **Streak counting.** Reads the past 14 days of manual test logs and sensor data. Counts consecutive days with ammonia = 0 AND nitrite = 0. Writes this streak count to a rolling state file: `state/cycle_state.json`.

2. **Phase classification.** Based on streak length and historical readings, classifies the tank into one of five phases: `CYCLING_EARLY`, `CYCLING_ACTIVE`, `CYCLING_PLATEAU`, `CYCLE_COMPLETE_UNCONFIRMED`, or `CYCLE_CONFIRMED`. Phase transitions require two consecutive days of confirmation. Writes current phase to `cycle_state.json`.

3. **Plateau detection.** If nitrite has not decreased by more than 0.25 ppm over any 4-day window during active cycling, flags a `PLATEAU_ALERT` with duration in days and recommends Toby consider a small water change or ammonia dose check.

4. **Shrimp-ready notification.** When streak reaches 5 consecutive days of clean readings and phase is `CYCLE_CONFIRMED`, fires a single Telegram notification via call-toby (normal urgency): "Media Luna is shrimp-ready. 5 clean days in a row. Your call, Toby."

5. **Output.** Writes a one-paragraph cycle status summary to `state/cycle_summary.txt` for daily-log to optionally pull in.

**Risk:** Low. Read-only except for state files. No control over hardware. One notification gated behind a 5-day threshold.
