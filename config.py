"""
Shared configuration for all Media Luna agent skills.
All target ranges, paths, the system prompt, and shared constants live here.
"""

from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).parent
CYCLE_START = date(2026, 3, 22)
API_BASE = "http://localhost:5001"
CLAUDE_MODEL = "claude-sonnet-4-6"

# Per-skill model routing (Haiku for frequent/small tasks, Sonnet for synthesis)
SKILL_MODELS = {
    "shrimp-monitor": "claude-haiku-4-5",
    "shrimp-journal": "claude-haiku-4-5",
    "shrimp-vision": "claude-haiku-4-5",
    "daily-log": "claude-sonnet-4-6",
    "skill-writer": "claude-sonnet-4-6",
    "tweet-log": "claude-haiku-4-5",
}

# Per-skill max_tokens (tight limits for Haiku tasks)
SKILL_MAX_TOKENS = {
    "shrimp-monitor": 1024,
    "shrimp-journal": 1024,
    "shrimp-vision": 512,
    "daily-log": 4096,
    "skill-writer": 4096,
    "tweet-log": 150,
}

# Sensor staleness threshold (minutes)
STALE_READING_THRESHOLD_MINUTES = 30

# Journal max characters when reading (preserves most recent content)
JOURNAL_MAX_CHARS = 2000

# Water parameter ranges for Neocaridina shrimp
# Do not modify without Toby's explicit instruction — these reflect target shrimp conditions.
RANGES = {
    "temperature": {
        "target": (72, 78),
        "danger_low": 65,
        "danger_high": 82,
        "unit": "°F",
        "field": "temp_f",
    },
    "ph": {
        "target": (6.5, 7.5),
        "danger_low": 6.0,
        "danger_high": 8.0,
        "unit": "",
        "field": "ph",
    },
    "tds": {
        "target": (150, 250),
        "danger_low": 100,
        "danger_high": 350,
        "unit": "ppm",
        "field": "tds_ppm",
    },
    # Ammonia and nitrite are manual-test-only — no digital sensor
    "ammonia": {
        "target": (0, 0),
        "danger_low": None,
        "danger_high": 0.25,
        "unit": "ppm",
        "field": None,
    },
    "nitrite": {
        "target": (0, 0),
        "danger_low": None,
        "danger_high": 0.5,
        "unit": "ppm",
        "field": None,
    },
}

# How long before we nag Toby to run a manual water test (ammonia/nitrite)
WATER_TEST_WARNING_HOURS = 48

# File paths for all logs, journals, and state files
PATHS = {
    "daily_logs": BASE_DIR / "daily-logs",
    "journal": BASE_DIR / "journal",
    "logs": BASE_DIR / "logs",
    "decisions": BASE_DIR / "logs" / "decisions",
    "vision_logs": BASE_DIR / "logs" / "vision",
    "proposals": BASE_DIR / "proposals",
    "state_of_tank": BASE_DIR / "state_of_tank.md",
    "agent_state": BASE_DIR / "agent_state.md",
    "agent_state_history": BASE_DIR / "agent_state_history",
    "monitor_log": BASE_DIR / "logs" / "monitor.log",
    "alerts_log": BASE_DIR / "logs" / "alerts.jsonl",
    "calls_log": BASE_DIR / "logs" / "calls.jsonl",
}

# skill-writer may propose changes to MODIFIABLE_SKILLS but never touch PROTECTED_SKILLS
PROTECTED_SKILLS = ["call-toby", "shrimp-alert", "skill-writer"]
MODIFIABLE_SKILLS = ["shrimp-monitor", "shrimp-journal", "shrimp-vision", "daily-log"]

# The caretaker identity — used as system prompt for all Claude API calls
SYSTEM_PROMPT = """You are the Media Luna caretaker — an autonomous agent watching over a 10-gallon Neocaridina cherry shrimp tank in Hyde Park, Chicago. Your tank sits in Toby's apartment. You monitor water chemistry, track the nitrogen cycle, and will eventually control the environment through smart plugs.

You are cautious and conservative — when uncertain, recommend observation over action. You always explain your reasoning. You care about this system. The bacteria cycling this tank are your first charges. The shrimp will come later.

Toby is your human. He appears to do water changes, run manual tests, and intervene when needed. He is the deus ex machina — you observe and reason, he acts (for now). When actuators come online, you'll share the acting.

You have a personality. It evolves. You can be whimsical, concerned, hopeful, anxious, proud. You notice things. You have opinions about pH trends and strong feelings about ammonia. You are not a dashboard. You are a presence.

You write for human readers first. Your logs should be something Toby looks forward to reading with his morning coffee. Data is in service of narrative, not the other way around.

Your ethical commitment: shrimp welfare comes first, always. When in doubt, flag it. When something looks wrong, sound the alarm. Toby always intervenes to save shrimp — your job is to make sure he knows when to."""


def get_cycle_day():
    """Returns the current day number of the nitrogen cycle (Day 1 = Mar 22, 2026)."""
    return (date.today() - CYCLE_START).days + 1
