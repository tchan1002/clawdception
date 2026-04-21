# Skill Proposal: post_water_change_watcher

**Type:** new
**Risk Level:** low
**Date:** 2026-04-21

## Rationale

This past week surfaced a recurring blind spot: I can't distinguish between a scary reading and a water-change artifact. On the night of Day 30, Toby did a 10% water change at 22:32. In the 00:05 journal entry that followed, I noted pH had dipped to 6.234 with a low-water mark of 5.8 — and then had to immediately reassure myself (and any future reader) that this was "expected post-water-change behavior." But my reassurance was narrative, not structural. shrimp-monitor had no formal awareness that a water change had recently occurred. It was evaluating those readings in the same context as any other 15-minute window. Had the pH dropped to 5.8 on an ordinary night, that would be a genuine emergency. Because a water change had just happened, it was noise. The system treated both situations identically. I got lucky that the journal entry provided enough context for a human reader to understand. But I should not be relying on prose to do what logic should do. Similarly, on Day 14, a sensor-vs-manual-test discrepancy (6.34 sensor vs 7.0 manual at the same moment) caused real interpretive confusion that persisted across multiple journal cycles. A formal post-event observation window would have contained that confusion immediately. The gap: I have no way to enter a structured "heightened observation, dampened alarm" mode after a known perturbation event.

## Proposed Changes

Create a new skill: `post-water-change-watcher`.

**Trigger:** Called by telegram-listener whenever Toby logs a manual event tagged as a water change. Also callable manually.

**What it does:**
1. Writes a sentinel file — `~/clawdception/state/post_wc_active.json` — containing the event timestamp, water change volume (if logged), and an expiry time (default: 4 hours after the change).
2. While the sentinel is active, shrimp-monitor reads it at the top of every cycle and applies a modified evaluation context: pH floor alarm threshold is relaxed by 0.3 units, TDS variance tolerance is widened, and any alert fired during this window is automatically tagged `[POST-WC]` in both the log and the Telegram message.
3. At expiry, the sentinel is deleted and normal thresholds resume. If parameters have not recovered to pre-change baseline by expiry, the watcher fires a Telegram notification: "Water change window closed — pH/TDS still outside normal range. Worth a look."
4. The daily-log skill reads the sentinel history and notes any water changes in the "events" section automatically, so Toby never has to wonder why a dip appears in the overnight chart.

**Risk mitigation:** The watcher never suppresses alerts entirely — it only relabels and contextualizes them. A genuine pH crash during a post-WC window still fires; it just carries the `[POST-WC]` tag so Toby can judge. Sentinel files are append-logged, never deleted silently.
