---
name: document
description: Update REFERENCE.md, skill SKILL.md files, and CLAUDE.md to reflect changes made this session
---

Read session context. Update docs to reflect what changed. Safe to run when nothing changed — just verify docs are accurate and exit.

All writes use caveman style: drop articles, fragments ok, short synonyms. Technical substance exact. Code blocks unchanged.

## What to update

**REFERENCE.md** — arch/file map. Update if:
- New file added or removed
- New skill created
- Data flow changed
- New config constant or path added

**`skills/<name>/SKILL.md`** — per-skill doc. Update if:
- Skill behavior changed
- New inputs/outputs
- New dependencies
- Trigger conditions changed

**`CLAUDE.md`** — coding agent instructions. Update if:
- New project state (tank events, dates, colony status)
- A mistake was made and corrected — add a "do not" or "always" rule so it won't repeat
- A non-obvious approach was validated — record it so future Claude doesn't second-guess it
- A hard rule was clarified or a new constraint discovered

Do NOT add to CLAUDE.md:
- Code patterns derivable from reading the code
- Things already documented
- Anything ephemeral to this session

## How to proceed

1. Read each doc that may be affected
2. Compare against what changed this session
3. Write targeted updates — only what's wrong or missing
4. If nothing changed that affects a doc, leave it alone
