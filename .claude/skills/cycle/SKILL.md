---
name: cycle
description: Show the current nitrogen cycle status for Media Luna
---

Show the current nitrogen cycle status for Media Luna.

Run these in order:

1. Calculate today's cycle day — tank started March 22, 2026. Print "Day N of nitrogen cycle."
2. `curl -s "http://localhost:5001/api/events?type=water_test&limit=1"` — last manual water test
3. Read `state_of_tank.md` — rolling tank state summary
4. Read the last 3 lines of today's decision log at `logs/decisions/$(date +%Y-%m-%d).jsonl` (skip if file doesn't exist)

Report:
- Cycle day and a one-line note on where we typically are at this stage (e.g. nitrite spike, nitrite crash, stabilizing)
- Hours since last water test — flag with a warning if >48 hours
- Ammonia and nitrite from the last water test (the key cycling parameters)
- Current risk level and reasoning from the most recent agent decision
- Any watch items from state_of_tank.md worth flagging
