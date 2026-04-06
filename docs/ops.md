# Ops Reference — Pi Deployment & System Management

## Flask Server (systemd)

```bash
sudo systemctl restart media-luna.service
sudo systemctl status media-luna.service
sudo journalctl -u media-luna.service -f
```

After editing `sensor_server.py`, restart the service and run the smoke test:
```bash
bash scripts/smoke_test.sh
# From laptop targeting Pi:
bash scripts/smoke_test.sh http://192.168.12.76:5001
```

## SSH / SCP

```bash
ssh pi@192.168.12.76
# or
ssh pi@media-luna.local
```

**Agents must not run SCP — the user deploys manually.**
```bash
# Push entire repo to Pi (user runs this)
scp -r ~/clawdception pi@192.168.12.76:~/clawdception

# Push specific file (user runs this)
scp ~/clawdception/sensor_server.py pi@192.168.12.76:~/clawdception/sensor_server.py
```

## Crontab

```bash
# Review before installing
cat ~/clawdception/crontab.txt

# Install (replaces existing crontab)
crontab ~/clawdception/crontab.txt

# Verify
crontab -l
```

## Environment Variables

Set in `/etc/environment` and `/etc/systemd/system/media-luna.service`.  
For interactive SSH sessions: `source /etc/environment`

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API — required by all skills |
| `TELEGRAM_BOT_TOKEN` | call-toby notifications |
| `TELEGRAM_CHAT_ID` | call-toby target chat |

## Git Workflow

```bash
# Pi auto-pushes hourly via cron. Manual push:
cd ~/clawdception && git add -A && git commit -m "message" && git pull --rebase -X theirs origin main && git push origin main

# Pull latest on Pi without overwriting logs/db/agent state:
# Use the /sync Claude Code skill
```

## First-Time Pi Setup

```bash
cd ~/clawdception
./setup.sh
python3 skills/call_toby/run.py --test
```

## Skill Testing

```bash
cd ~/clawdception
python3 skills/shrimp_monitor/run.py --force
python3 skills/shrimp_journal/run.py
python3 skills/daily_log/run.py
python3 skills/daily_log/run.py --date 2026-03-30   # backfill specific date
python3 skills/call_toby/run.py --test

# Unit tests (no server or hardware required)
python3 -m pytest tests/ -v
```
