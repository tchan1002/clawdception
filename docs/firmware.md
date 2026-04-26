# Firmware Reference — ESP32 Sensor Hub

## Arduino Commands

arduino-cli is installed on the **Mac** (not the Pi). Flash from there.

```bash
# Compile only (safe to run anytime)
arduino-cli compile --fqbn esp32:esp32:esp32 ~/clawdception/media_luna_sensor_hub

# Upload to ESP32 sensor hub (flashes device — confirm with user before running)
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/cu.usbserial-0001 ~/clawdception/media_luna_sensor_hub

# Upload to ESP32-CAM (flashes device — confirm with user before running)
arduino-cli upload --fqbn esp32:esp32:esp32cam --port /dev/cu.usbserial-110 ~/clawdception/esp32_cam

# Monitor ESP32-CAM serial output
arduino-cli monitor --port /dev/cu.usbserial-110 --config baudrate=115200
```

Serial monitor settings for ESP32-CAM (`/dev/cu.usbserial-110`):
```
baudrate=115200, bits=8, parity=none, stop_bits=1, dtr=on, rts=on
```

**Sensor hub** USB port: `/dev/cu.usbserial-0001`  
**ESP32-CAM** USB port: `/dev/cu.usbserial-110`  
**Always compile before suggesting an upload.**  
**Do not run upload without explicit user instruction.**

## Wiring

| Sensor | Pin | Notes |
|--------|-----|-------|
| DS18B20 (temp) data | GPIO 4 | 4.7kΩ pullup to 3.3V required |
| DFRobot pH v2 signal | GPIO 34 (ADC1) | Analog input |
| DFRobot TDS signal | GPIO 35 (ADC1) | Analog input |

WiFi target: `http://192.168.12.76:5001/api/sensors` — SSID: Shroomies  
Reading interval: 900,000 ms (15 min) — **do not change without asking**

## Sensor Calibration

**Do not modify calibration constants without explicit user instruction.**  
These were set against physical calibration solutions.

### pH (last calibrated: March 30, 2026)

| Buffer | Measured Voltage |
|--------|----------------|
| pH 7.0 | 1.37V |
| pH 4.0 | 1.88V |

- Offset applied: `-1.10` (matched to API test kit reading of 6.4)
- Temperature compensation: `+0.003 pH per °C`

### TDS
DFRobot temperature-compensated formula. No custom offset.

### Temperature (DS18B20)
Factory spec ±0.5°C. No custom offset.

## JSON Payload Structure

```json
{
  "temp_c": 23.5, "temp_f": 74.3, "ph": 6.8, "tds_ppm": 187,
  "debug": {
    "ph_raw_adc": 1750, "ph_voltage": 1.37,
    "ph_pre_offset": 7.9, "tds_raw_adc": 2100, "tds_voltage": 1.69
  },
  "system": {
    "wifi_rssi": -58, "heap_free": 215000, "uptime_ms": 3600000,
    "reading_count": 4, "reconnect_count": 0, "failure_count": 0
  },
  "calibration": {
    "ph_offset": -1.10, "ph_neutral_voltage": 1.37,
    "ph_acid_voltage": 1.88, "temp_compensation": 0.003
  }
}
```

- Top-level values: calibrated, for agent consumption
- `debug`: raw ADC/voltage for drift detection — **do not remove this section**
- `system`: ESP32 health metrics
- `calibration`: coefficients currently applied

When editing `.ino` files, preserve the existing comment structure (calibration notes, wiring annotations, JSON payload docs — these are intentional).
