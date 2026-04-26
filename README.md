# Clawdception

i've wanted to keep shrimp since i was a kid. a few weeks ago i finally did it.  
like any responsible shrimp dad, i built a baby monitor.

Media Luna is a 10-gallon cherry shrimp colony in Hyde Park, Chicago. Clawdception is the autonomous AI system watching over it 24/7 — reading water chemistry, reasoning about the colony's state, and writing daily journal entries i read with my tea.

---

## what it does

- **sensors** — ESP32 reads temperature, pH, and TDS every 15 minutes and posts to a Raspberry Pi 5 over WiFi
- **caretaker** — Claude API reasons about the sensor data, flags anomalies, and writes narrative logs about what's happening in the tank
- **telegram** — i can text the tank and it texts back. i get a daily log every morning.
- **twitter** — [@clawdception](https://twitter.com/clawdception) posts daily. the caretaker has its own voice.
- **dashboard** — live Chart.js trendlines at [clawdception.com](https://clawdception.com)

---

## stack

- Raspberry Pi 5 4GB — always-on brain
- ESP32-WROOM-32 — sensor hub
- DS18B20 (temp), DFRobot pH V2, DFRobot TDS
- Flask + SQLite on Pi, systemd service
- Claude API (Haiku for monitoring, Sonnet for daily logs)
- Tweepy for Twitter, python-telegram-bot for Telegram

---

## build log

Full documentation in the project files. Water chemistry logs, caretaker decision logs, and daily journal entries all tracked in GitHub.

Hosting house tours of the rig if you're in Hyde Park.
