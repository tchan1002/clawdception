# Skill: equipment-check

**What it does:** Hardware health check. Catches sensor-derivable equipment faults and tracks maintenance schedules. Logs a decision entry so the journal and daily-log pick it up. Fires Telegram alerts for any issue.

**When it runs:** Every 30 minutes via cron.

**Sensor-derivable checks:**
- DS18B20 temp probe error rate (`temp_raw_c == -127.0` in >10% of last 24h readings)
- ESP32 post failure count (elevated `post_failures`/`failure_count` in last hour ≥ 3)
- WiFi RSSI (mean < -75 dBm in last hour)
- Heap free (any reading < 80,000 bytes in last hour — potential memory leak)
- Uptime reset (latest `uptime_ms` < previous reading → unexpected reboot)
- pH probe drift (mean `(ph_pre_offset - ph)` deviates >0.15 pH from expected offset over 24h)
- ADC rail saturation (`ph_raw_adc` or `tds_raw_adc` == 0 or 4095 on latest reading)

**Schedule-based checks** (state in `logs/equipment_state.json`):
- pH probe recalibration — due every 30 days

**What it reads:**
- `GET /api/sensors?limit=96` — last 24h of readings (parses `raw_json` for debug/system/calibration fields)
- `logs/equipment_state.json` — maintenance dates and last-nag timestamps

**What it writes:**
- `logs/decisions/YYYY-MM-DD.jsonl` — decision entry (risk_level, reasoning, issues, notes)
- `logs/equipment_state.json` — updated nag timestamps
- Fires call-toby (warning) for each issue, at most once per 23hr per issue key

**Nag cooldown:** 23 hours per issue key — won't spam the same alert twice a day.

**State file schema:**
```json
{
  "ph_probe_last_calibrated": "YYYY-MM-DD",
  "last_nag": {
    "ds18b20_error": "2026-04-06T09:00:00",
    "wifi_rssi_low": "2026-04-06T09:00:00"
  }
}
```

**Issue keys:** `ds18b20_error`, `post_failures`, `wifi_rssi_low`, `heap_low`, `uptime_reset`, `ph_probe_drift`, `ph_adc_saturated`, `tds_adc_saturated`, `ph_probe_never_calibrated`, `ph_probe_overdue`

**To record maintenance:**
Edit `logs/equipment_state.json` directly after performing the task, e.g.:
```json
{ "ph_probe_last_calibrated": "2026-04-06" }
```

**Dependencies:** call-toby, utils.py, config.py

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/equipment_check/run.py --force
```

**Modifiable:** Yes.
