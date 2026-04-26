Clawdception

i've wanted to keep shrimp since i was a kid. a few weeks ago i finally did it.

like any responsible shrimp dad, i built a baby monitor.

Media Luna is a 10-gallon cherry shrimp colony in Hyde Park, Chicago. Clawdception is the autonomous AI system watching over it 24/7 — reading water chemistry, reasoning about the colony's state, and writing daily journal entries i read with my tea.

what it does

sensors — ESP32 reads temperature, pH, and TDS every 15 minutes and posts to a Raspberry Pi 5 over WiFi

caretaker — Claude API reasons about the sensor data, flags anomalies, and writes narrative logs about what's happening in the tank

telegram — i can text the tank and it texts back. i get a daily log every morning.

twitter — @clawdception posts daily. the caretaker has its own voice.

dashboard — live Chart.js trendlines at www.clawdception.com

stack

raspberry pi 5 4gb — always-on brain

esp32-wroom-32 — sensor hub

ds18b20 (temp), dfrobot ph v2, dfrobot tds

flask + sqlite on pi, systemd service

claude api (haiku for monitoring, sonnet for daily logs)

tweepy for twitter, python-telegram-bot for telegram

build log

full documentation in the project files. water chemistry logs, caretaker decision logs, and daily journal entries all tracked in github.
hosting house tours of the rig if you're in hyde park!
