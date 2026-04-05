---
name: status
description: Check the current health of the Media Luna system
---

Check the current health of the Media Luna system and report a brief status summary.

Run these in order:

1. `curl -s http://localhost:5001/api/health` — server alive + last reading timestamp
2. `curl -s http://localhost:5001/api/sensors/latest` — current temp/pH/TDS values
3. `sudo systemctl status media-luna.service --no-pager -l` — service state
4. Read the last 5 lines of `logs/monitor.log` — recent agent decisions

Report:
- Whether the Flask server is responding and the systemd service is active
- Current temp / pH / TDS and whether each is in target range (Temp 72–78°F, pH 6.5–7.5, TDS 150–250 ppm)
- How long ago the last sensor reading arrived (flag if >30 min — ESP32 may be offline)
- Last risk level from monitor.log (green / yellow / red)
