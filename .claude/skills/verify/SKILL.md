---
name: verify
description: Test a newly implemented feature live, assess results, and write a test to tests/
---

You just implemented a feature this session. Verify it works and write a test.

## Steps

**1. Identify the feature**
Read the session context — what was just built or changed? What is it supposed to do?

**2. Call it live**
Exercise the feature by running real code against the live system. Use `python3 -c "..."` or run a script directly. Pick inputs that cover the core behavior and at least one edge case (e.g. missing data, failure path).

Example for question answering:
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from skills.telegram_listener.run import answer_question
print(answer_question('how are the shrimp doing?'))
"
```

**3. Assess results**
Did the output match expected behavior? Look for:
- Correct return type / structure
- Expected content (right data used, right format)
- No tracebacks or silent failures
- Edge cases handled correctly

Report what passed and what (if anything) looks wrong.

**4. Write a test**
Read `tests/` to find the right file to append to, or create a new `tests/test_<skill>.py` if none exists.

Look at existing tests for style. Write a test that:
- Mocks external calls (Claude API, HTTP requests, DB)
- Asserts the core behavior you just verified live
- Covers the failure/edge case you tested

Run `python3 -m pytest tests/ -v` — all must pass before done.
