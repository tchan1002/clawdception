# Skill: skill-writer

**What it does:** Once a week, reflects on the past 7 days of logs and proposes ONE new skill or ONE modification to an existing skill. Writes the full proposal to `~/clawdception/proposals/`. Never modifies existing skills directly — all changes require Toby's manual review and approval.

**When it runs:** Sundays at 8:00 AM via cron.

**What it reads:**
- Last 7 daily logs
- Last 7 days of journal entries
- All current SKILL.md files (to understand what already exists)

**What it writes:**
- A proposal directory: `~/clawdception/proposals/YYYY-MM-DD-{skill-name}/`
  - `SKILL.md` — proposed skill spec (new or modified)
  - `run.py` — proposed implementation
  - `rationale.md` — why this skill, with specific log references
  - `diff.md` — if modifying existing skill, what changed and why

**Constraints:**
- NEVER directly modifies files in `skills/`
- NEVER proposes changes to: call-toby, shrimp-alert, skill-writer (protected skills)
- NEVER proposes changes to `config.py` target ranges (Toby's call)
- NEVER proposes skills that execute actuator commands without explicit enablement

**How to run manually:**
```bash
cd ~/clawdception
python3 skills/skill_writer/run.py
```

**Reviewing proposals:**
```bash
ls ~/clawdception/proposals/
cat ~/clawdception/proposals/YYYY-MM-DD-{name}/rationale.md
```

To install a proposal: review it, then manually copy it to the appropriate `skills/` directory.

**Protected:** Yes. skill-writer may never propose changes to itself.
