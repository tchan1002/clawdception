---
name: sync
description: Pull latest code from remote without overwriting logs, database, or agent state
---

Pull the latest code from the remote repo while preserving all local runtime data.
These files are intentionally tracked in git but must never be clobbered by a remote
pull — the Pi's copies are always the truth.

**Protected paths (never overwrite):**
- `logs/` — monitor.log, decisions/, spend.jsonl, calls.jsonl, all agent logs
- `media_luna.db` — live SQLite database
- `daily-logs/` — agent-written daily summaries
- `journal/` — agent journal entries
- `agent_state.md` — agent's current working memory
- `agent_state_history/` — historical agent state snapshots
- `state_of_tank.md` — agent's running assessment of tank condition

Run the following steps in order:

**Step 1 — Back up protected runtime files to /tmp:**
```bash
rm -rf /tmp/ml_sync_backup
mkdir -p /tmp/ml_sync_backup
cp -r /home/pi/clawdception/logs /tmp/ml_sync_backup/
cp /home/pi/clawdception/media_luna.db /tmp/ml_sync_backup/
cp -r /home/pi/clawdception/daily-logs /tmp/ml_sync_backup/
cp -r /home/pi/clawdception/journal /tmp/ml_sync_backup/
cp /home/pi/clawdception/agent_state.md /tmp/ml_sync_backup/
cp -r /home/pi/clawdception/agent_state_history /tmp/ml_sync_backup/
cp /home/pi/clawdception/state_of_tank.md /tmp/ml_sync_backup/
echo "Backup complete."
```

**Step 2 — Stash all tracked local changes so git pull is clean:**
```bash
cd /home/pi/clawdception && git stash
```

**Step 3 — Pull latest from remote (rebase Pi's commits on top):**
```bash
cd /home/pi/clawdception && git pull --rebase
```

**Step 4 — Restore protected runtime files from backup (overwrite whatever was pulled):**
```bash
cp -r /tmp/ml_sync_backup/logs/. /home/pi/clawdception/logs/
cp /tmp/ml_sync_backup/media_luna.db /home/pi/clawdception/media_luna.db
cp -r /tmp/ml_sync_backup/daily-logs/. /home/pi/clawdception/daily-logs/
cp -r /tmp/ml_sync_backup/journal/. /home/pi/clawdception/journal/
cp /tmp/ml_sync_backup/agent_state.md /home/pi/clawdception/agent_state.md
cp -r /tmp/ml_sync_backup/agent_state_history/. /home/pi/clawdception/agent_state_history/
cp /tmp/ml_sync_backup/state_of_tank.md /home/pi/clawdception/state_of_tank.md
echo "Runtime files restored."
```

**Step 5 — Drop the stash (it contained only the runtime files we just restored):**
```bash
cd /home/pi/clawdception && git stash drop 2>/dev/null || true
```

**Step 6 — Show what changed:**
```bash
cd /home/pi/clawdception && git log --oneline -5
```

Report:
- Whether the pull succeeded and how many commits were fetched
- Which files changed (code only — skip logs/db churn)
- Any errors encountered
- Confirm protected files were restored
