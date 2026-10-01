# clawdception

baby monitor for a 10 gallon cherry shrimp tank in hyde park, chicago.

## what it does

- **sensors** — ESP32 reads temperature, pH, and TDS every 15 minutes and posts to a Raspberry Pi 5 over WiFi
- **caretaker** — Claude API reasons about the sensor data, flags anomalies, pings me for equipment maintenance, and writes narrative logs about what's happening in the tank
- **telegram** — I can text the tank and it texts back.
- **twitter** — [@clawdception](https://twitter.com/clawdception1) posts daily. 
- **dashboard** — live Chart.js trendlines at [clawdception.com](https://clawdception.com)

## stack

- Raspberry Pi 5 4GB — always-on brain
- ESP32-WROOM-32 — sensor hub
- DS18B20 (temp), DFRobot pH V2, DFRobot TDS
- Flask + SQLite on Pi, systemd service
- Claude API (Haiku for monitoring, Sonnet for daily logs)
- Tweepy for Twitter, python-telegram-bot for Telegram
