# Skill: tweet-log

**What it does:** Posts tank status to Twitter. Runs in three modes: a one-time intro post, a daily thread from the morning daily log, and reactive throwaway posts after manual events.

**When it runs:** 7:05 AM daily via cron (daily mode). Throwaway mode can be triggered manually after notable events.

**Modes:**
- `intro` — one-time introductory post, hardcoded text, no Claude call
- `daily` — posts yesterday's daily log as a tweet thread, verbatim, no Claude call
- `throwaway` — calls Claude to write a short reactive post (2–3 per day max) based on agent_state, state_of_tank, and recent daily logs

**What it reads:**
- `state_of_tank.md` — current tank condition (throwaway mode)
- `agent_state.md` — caretaker personality/disposition (throwaway mode)
- Last 3 daily logs via `read_daily_logs()` (throwaway mode)
- Today's daily log file (daily mode)

**What it writes:**
- Posts to Twitter via `tweepy` (requires `TWITTER_*` env vars)
- `logs/tweet_log.log` — stdout from cron run

**Token budget:** 150 tokens max (Haiku, tight constraint for tweet length).

**Dependencies:** utils.py, config.py, tweepy

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/tweet_log/run.py --mode daily
python3 skills/tweet_log/run.py --mode throwaway
```

**Modifiable:** Yes.
