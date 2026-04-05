"""
skill-writer — weekly self-improvement proposal generator.

Reads the past week of logs, reflects on gaps, proposes ONE new or modified skill.
Writes the proposal to ~/clawdception/proposals/ for Toby's review.
NEVER modifies existing skills directly.

Usage:
    python3 run.py
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import MODIFIABLE_SKILLS, PATHS, PROTECTED_SKILLS, get_cycle_day
from utils import call_claude, read_daily_logs
from skills.call_toby.run import call_toby

# Tool definition for skill proposal
TOOL = {
    "name": "propose_skill_change",
    "description": "Propose a new skill or modification to an existing skill",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of skill to modify, or 'new' for a new skill"
            },
            "proposal_type": {
                "type": "string",
                "enum": ["modify", "new"],
                "description": "Whether this is a modification or new skill"
            },
            "rationale": {
                "type": "string",
                "description": "Why this skill is needed, with specific examples from past week"
            },
            "proposed_changes": {
                "type": "string",
                "description": "What to change or what the new skill does"
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Risk level of implementing this change"
            }
        },
        "required": ["skill_name", "proposal_type", "rationale", "proposed_changes", "risk_level"]
    }
}


def read_week_journals():
    """Returns concatenated journal entries from the past 7 days (truncated to fit)."""
    journal_dir = PATHS["journal"]
    entries = []
    today = date.today()
    for i in range(1, 8):
        d = today - timedelta(days=i)
        path = journal_dir / f"{d}.md"
        if path.exists():
            text = path.read_text()
            # Truncate each day's journal to keep total tokens manageable
            entries.append(f"### {d}\n{text[:400]}")
    return "\n\n".join(entries) or "No journal entries in the past 7 days."


def read_all_skill_specs():
    """Returns a summary of all current SKILL.md files."""
    skills_dir = Path(__file__).parent.parent
    skill_summaries = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                # First 300 chars of each skill spec
                text = skill_md.read_text()[:300]
                skill_summaries.append(f"**{skill_dir.name}**:\n{text}")
    return "\n\n".join(skill_summaries) or "No skills found."


MIN_DAILY_LOGS = 7        # don't run until we have enough history to reason from
MIN_DAYS_BETWEEN = 7      # don't propose more than once a week


def should_run():
    """
    Returns (bool, reason). Conditions:
    - At least MIN_DAILY_LOGS daily logs exist
    - At least MIN_DAYS_BETWEEN days since last proposal
    """
    log_count = len(list(PATHS["daily_logs"].glob("*.md"))) if PATHS["daily_logs"].exists() else 0
    if log_count < MIN_DAILY_LOGS:
        return False, f"only {log_count}/{MIN_DAILY_LOGS} daily logs — not enough history yet"

    proposals_dir = PATHS["proposals"]
    if proposals_dir.exists():
        proposal_dirs = sorted(proposals_dir.iterdir(), reverse=True)
        if proposal_dirs:
            # Proposal dirs are named YYYY-MM-DD-{name}
            last_proposal_date_str = proposal_dirs[0].name[:10]
            try:
                last_date = date.fromisoformat(last_proposal_date_str)
                days_since = (date.today() - last_date).days
                if days_since < MIN_DAYS_BETWEEN:
                    return False, f"last proposal was {days_since} days ago (min {MIN_DAYS_BETWEEN})"
            except ValueError:
                pass

    return True, f"{log_count} daily logs available, conditions met"


def run(force=False):
    today = date.today()
    cycle_day = get_cycle_day()

    ok, reason = should_run()
    if not force and not ok:
        print(f"[skill-writer] Skipping — {reason}")
        return

    print(f"[skill-writer] Running — {reason} (Day {cycle_day} of cycle)")

    daily_logs = read_daily_logs(7)
    journals = read_week_journals()
    skill_specs = read_all_skill_specs()

    logs_text = ""
    for i, log in enumerate(daily_logs[:5]):
        logs_text += f"\n--- Daily log {i+1} ---\n{log[:500]}\n"
    logs_text = logs_text or "No daily logs yet."

    prompt = f"""You are the Media Luna caretaker on Day {cycle_day} of the nitrogen cycle.

You are reviewing the past week of your own logs and proposing an improvement to your skill set.

CURRENT SKILLS:
{skill_specs}

PAST WEEK — DAILY LOGS (excerpts):
{logs_text}

PAST WEEK — JOURNAL EXCERPTS:
{journals}

---

PROTECTED SKILLS (never propose changes to these): {', '.join(PROTECTED_SKILLS)}
MODIFIABLE SKILLS (can propose changes): {', '.join(MODIFIABLE_SKILLS)}
You may also propose an entirely new skill.

---

Task: Identify ONE gap in your current capabilities. Something you keep noticing but can't respond to. A pattern you can observe but not act on. Information you wish you had.

Propose ONE concrete change: either a new skill or a modification to an existing skill.
The proposal must reference a specific situation from the past week where this skill would have changed a decision.

Use the tool to submit your proposal with:
- skill_name: the name of the skill to modify (or a name for a new skill)
- proposal_type: "modify" or "new"
- rationale: why this change is needed (150-250 words, reference specific situations)
- proposed_changes: detailed description of what should change or what the new skill should do
- risk_level: "low", "medium", or "high" based on potential impact"""

    try:
        result = call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="skill-writer",
            tools=[TOOL],
            tool_name=TOOL["name"],
        )
    except Exception as e:
        print(f"[skill-writer] Claude call failed: {e}")
        return

    # --- Write proposal ---
    skill_name = re.sub(r'[^a-z0-9-]', '', result["skill_name"].lower().replace(" ", "-"))
    proposal_dir = PATHS["proposals"] / f"{today}-{skill_name}"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    # Write proposal files
    (proposal_dir / "proposal.md").write_text(f"""# Skill Proposal: {result['skill_name']}

**Type:** {result['proposal_type']}
**Risk Level:** {result['risk_level']}
**Date:** {today}

## Rationale

{result['rationale']}

## Proposed Changes

{result['proposed_changes']}
""")

    print(f"[skill-writer] Proposal written to {proposal_dir}")

    call_toby(
        f"New skill proposal: {skill_name} 🛠️  Review at ~/clawdception/proposals/{today}-{skill_name}/",
        urgency="info"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run regardless of conditions")
    args = parser.parse_args()
    run(force=args.force)
