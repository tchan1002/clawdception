"""
skill-writer — weekly self-improvement proposal generator.

Reads the past week of logs, reflects on gaps, proposes ONE new or modified skill.
Writes the proposal to ~/clawdception/proposals/ for Toby's review.
NEVER modifies existing skills directly.

Usage:
    python3 run.py
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import MODIFIABLE_SKILLS, PATHS, PROTECTED_SKILLS, get_cycle_day
from utils import call_claude, read_daily_logs
from skills.call_toby.run import call_toby


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

Respond with exactly four sections delimited as shown:

===RATIONALE===
[Why this skill? Reference specific journal entries or log situations. 150-250 words. Explain what decision would have been different.]

===SKILL_MD===
[Full SKILL.md content for the proposed skill or modified skill]

===RUN_PY===
[Full run.py implementation. Clean, functional Python. No classes unless needed.]

===DIFF_MD===
[If modifying an existing skill: what changed and why. If new skill: write "New skill — no diff."]"""

    try:
        response = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
        )
    except Exception as e:
        print(f"[skill-writer] Claude call failed: {e}")
        return

    # --- Parse sections ---
    sections = {}
    current_key = None
    current_lines = []
    for line in response.splitlines():
        if line.strip() in ("===RATIONALE===", "===SKILL_MD===", "===RUN_PY===", "===DIFF_MD==="):
            if current_key and current_lines:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line.strip()
            current_lines = []
        else:
            if current_key:
                current_lines.append(line)
    if current_key and current_lines:
        sections[current_key] = "\n".join(current_lines).strip()

    rationale = sections.get("===RATIONALE===", "")
    skill_md = sections.get("===SKILL_MD===", "")
    run_py = sections.get("===RUN_PY===", "")
    diff_md = sections.get("===DIFF_MD===", "")

    if not skill_md or not run_py:
        print("[skill-writer] Could not parse proposal from Claude response")
        print(response[:500])
        return

    # --- Infer skill name from SKILL.md ---
    skill_name = "unnamed-skill"
    for line in skill_md.splitlines():
        if line.startswith("# Skill:"):
            skill_name = line.replace("# Skill:", "").strip().lower().replace(" ", "-")
            break

    # --- Write proposal ---
    proposal_dir = PATHS["proposals"] / f"{today}-{skill_name}"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    (proposal_dir / "SKILL.md").write_text(skill_md)
    (proposal_dir / "run.py").write_text(run_py)
    (proposal_dir / "rationale.md").write_text(rationale)
    (proposal_dir / "diff.md").write_text(diff_md)

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
