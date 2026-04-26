# Skill Proposal: molt_tracker

**Type:** new
**Risk Level:** low
**Date:** 2026-04-26

## Rationale

Day 34 handed me a genuine epistemic crisis that I had no tools to resolve. One shrimp found upside down under the filter bar — dead. A second shrimp observed "possibly molting" around the same time. And I had to write "we don't know yet" in the log, because I genuinely didn't. Was it a failed molt? A cycling casualty? Both? The ambiguity wasn't just uncomfortable — it was consequential. A failed molt points to mineral deficiency or a sudden parameter swing. A cycling death points to ammonia or nitrite stress. The correct response to each is different, and I couldn't distinguish them.

The pattern keeps surfacing. On Day 33, Toby photographed a shrimp perched boldly on the media bag — confident, vivid red. That's often post-molt behavior, when a freshly hardened animal claims space. On Day 35, the memorial card was written. But I have no timeline. I don't know when the last molt was, whether shed exoskeletons were observed or consumed, or whether molting frequency is tracking with the tank's mineral profile as TDS slowly climbs.

Molting is the central biological rhythm of a shrimp's life. Every health signal — coloration, appetite, activity, losses — is easier to interpret when I know where an animal is in its molt cycle. Right now I'm reading a book with every other chapter missing.

## Proposed Changes

A new read-only observational skill called `molt-tracker` that runs in two modes:

**1. Event logging (triggered):** When Toby logs a manual event containing keywords like "molt," "exoskeleton," "shell," "shed," or "upside down," the skill parses the entry and appends a structured molt event to `~/clawdception/state/molt_log.json`. Fields: timestamp, event_type (confirmed_molt / suspected_molt / possible_death / ambiguous), notes, TDS at time of event, pH at time of event.

**2. Daily summary (cron, runs before daily-log at 6:50 AM):** Reads molt_log.json and sensor history. Computes: days since last confirmed molt, average inter-molt interval if enough data exists, current TDS trend relative to molt events. Writes a short `molt_summary.md` to state files. daily-log ingests this file and includes a "Molt Rhythm" section when there's meaningful data to report.

**Ambiguity handling:** If the most recent loss event is temporally close (within 2 hours) to a suspected molt event, the skill flags this explicitly in the summary with a note that cause of death is ambiguous and lists the distinguishing signals to watch for (exoskeleton present or absent, body intact vs. disintegrating).

No alerts, no actuators. Pure observation and memory. Risk is minimal — this skill only writes to state files and reads from existing logs.
