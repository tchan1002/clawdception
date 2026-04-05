---
name: logs
description: Tail recent logs from all Media Luna agent skills and surface errors
---

Tail recent logs from all Media Luna agent skills and surface any errors or anomalies.

Read these files (skip gracefully if they don't exist):

1. Last 15 lines of `logs/monitor.log` — shrimp-monitor one-line summaries
2. Last 10 lines of `logs/journal.log` — shrimp-journal cron stdout
3. Last 10 lines of `logs/daily_log.log` — daily-log cron stdout
4. Last 10 lines of `logs/skill_writer.log` — skill-writer stdout
5. Last 5 entries of `logs/calls.jsonl` — call-toby log (parse JSON, show timestamp + message)
6. Last 5 entries of `logs/spend.jsonl` — token usage (parse JSON, show skill + total_tokens)

Report:
- Any ERROR lines or Python tracebacks visible in any log
- Current risk trend from monitor.log (improving / stable / worsening)
- Whether call-toby is sending via Telegram or falling back to log file
- Total tokens used across the last 5 spend entries and which skill is spending the most
