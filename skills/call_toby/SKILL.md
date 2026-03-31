# Skill: call-toby

**What it does:** Sends a notification to Toby via Telegram. This is the agent's voice — the way it reaches into the world outside the tank. Used for alerts, daily log teasers, water test reminders, and anything else worth a human's attention.

**When it runs:** Called by other skills. Not cron-scheduled itself.

**Urgency levels:**
- `info` (ℹ️) — observation worth noting, milestone, daily digest summary
- `warning` (⚠️) — parameter drifting, overdue manual test, check soon
- `critical` (🚨) — something might die, sensor failure, danger zone readings

**What it reads:** Nothing.

**What it writes:**
- Sends Telegram message if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
- Falls back to `~/clawdception/logs/calls.jsonl` + stdout if Telegram isn't configured

**Dependencies:** None. This is a foundational skill.

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/call_toby/run.py --test
# Should send "Media Luna test ping 🦐" to Telegram (or log to calls.jsonl)

python3 skills/call_toby/run.py --message "Hello from the tank" --urgency info
```

**How to import:**
```python
from skills.call_toby.run import call_toby
call_toby("pH is dropping", urgency="warning")
```

**Environment variables:**
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `TELEGRAM_CHAT_ID` — your Telegram user/chat ID

**Protected:** Yes. skill-writer may never propose changes to this skill.
