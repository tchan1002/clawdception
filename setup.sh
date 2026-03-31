#!/bin/bash
# setup.sh — initialize the Media Luna agent infrastructure on the Pi
# Run once after SCP'ing the repo to ~/clawdception on the Pi.

set -e
cd "$(dirname "$0")"

echo ""
echo "=== Media Luna Agent Setup ==="
echo ""

# --- Install Python dependencies ---
echo "[1/5] Installing Python dependencies..."
pip install anthropic requests --break-system-packages
echo "      Done."

# --- Create required directories ---
echo "[2/5] Creating directories..."
mkdir -p journal
mkdir -p daily-logs
mkdir -p logs/decisions
mkdir -p logs/vision
mkdir -p proposals
echo "      Done."

# --- Initialize state files if they don't exist ---
echo "[3/5] Initializing state files..."

if [ ! -f state_of_tank.md ]; then
    echo "      Creating state_of_tank.md..."
    cat > state_of_tank.md << 'EOF'
# State of Tank — Media Luna

**Last updated:** $(date +%Y-%m-%d)
**Status:** Cycling — no shrimp yet

No state recorded yet. Will be populated after first daily-log run.
EOF
    echo "      state_of_tank.md created."
else
    echo "      state_of_tank.md already exists — skipping."
fi

if [ ! -f agent_state.md ]; then
    echo "      Creating agent_state.md..."
    cat > agent_state.md << 'EOF'
# Agent State — Media Luna Caretaker

I'm new. I'm watching a tank of water with bacteria I can't see. I don't know what I'm doing yet, but I'm paying attention.
EOF
    echo "      agent_state.md created."
else
    echo "      agent_state.md already exists — skipping."
fi

# --- Check environment variables ---
echo "[4/5] Checking environment variables..."

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "      ⚠️  ANTHROPIC_API_KEY is not set."
    echo "      Add to ~/.bashrc or ~/.profile:"
    echo "        export ANTHROPIC_API_KEY=your_key_here"
else
    echo "      ✓  ANTHROPIC_API_KEY is set."
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "      ℹ️  TELEGRAM_BOT_TOKEN not set — call-toby will log to file only."
    echo "      To enable Telegram: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in ~/.bashrc"
else
    echo "      ✓  TELEGRAM_BOT_TOKEN is set."
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "      ℹ️  TELEGRAM_CHAT_ID not set."
else
    echo "      ✓  TELEGRAM_CHAT_ID is set."
fi

# --- Cron reminder ---
echo "[5/5] Cron setup..."
echo "      crontab.txt is ready for review. DO NOT auto-install."
echo "      When ready, install cron jobs with:"
echo "        crontab ~/clawdception/crontab.txt"
echo "      Or append to existing crontab:"
echo "        (crontab -l 2>/dev/null; cat ~/clawdception/crontab.txt) | crontab -"
echo ""
echo "      Make sure ANTHROPIC_API_KEY is exported in your shell environment"
echo "      before installing the crontab. Cron inherits env from the crontab file's"
echo "      ANTHROPIC_API_KEY line, so add it there too."
echo ""

echo "=== Setup complete ==="
echo ""
echo "Test call-toby:"
echo "  cd ~/clawdception && python3 skills/call_toby/run.py --test"
echo ""
echo "Test shrimp-monitor (requires live sensor data):"
echo "  cd ~/clawdception && python3 skills/shrimp_monitor/run.py"
echo ""
echo "Write today's daily log manually:"
echo "  cd ~/clawdception && python3 skills/daily_log/run.py"
echo ""
