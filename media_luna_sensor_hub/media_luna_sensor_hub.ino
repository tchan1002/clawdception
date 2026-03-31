/*
 * Media Luna — ESP32 Sensor Hub v2
 * Reads: DS18B20 temperature, DFRobot pH V2, DFRobot TDS
 * Posts: Rich JSON to Flask endpoint for AI agent consumption
 * 
 * WIRING:
 *   DS18B20 Data  → GPIO 4  (with 4.7kΩ pullup to 3.3V)
 *   pH Signal     → GPIO 34 (ADC1)
 *   TDS Signal    → GPIO 35 (ADC1)
 *   
 * TOOLCHAIN:
 *   arduino-cli compile --fqbn esp32:esp32:esp32 ~/clawdception/media_luna_sensor_hub
 *   arduino-cli upload  --fqbn esp32:esp32:esp32 --port /dev/cu.usbserial-0001 ~/clawdception/media_luna_sensor_hub
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ============================================================
// CONFIG
// ============================================================

const char* WIFI_SSID      = "Shroomies";
const char* WIFI_PASSWORD   = "AhnTheSpectrum69";
const char* SERVER_URL      = "http://192.168.12.76:5001/api/sensors";

// 900000 = 15 min (production), 30000 = 30s (testing)
const unsigned long READ_INTERVAL = 10000;

// ============================================================
// PIN ASSIGNMENTS — ADC1 ONLY (ADC2 broken with WiFi)
// ============================================================

#define DS18B20_PIN  4
#define PH_PIN       34
#define TDS_PIN      35

// ============================================================
// CALIBRATION — Mar 30, 2026
//   pH 7.0 buffer → 1.37V avg
//   pH 4.0 buffer → 1.88V avg
//   Offset: -1.10 (matched to API kit reading of 6.4)
//   Temp: DS18B20 factory spec ±0.5°C, no offset applied
//   TDS: DFRobot formula, no offset needed
// ============================================================

#define PH_NEUTRAL_V    1.37
#define PH_ACID_V       1.88
#define PH_OFFSET       -1.10

#define TDS_VREF        3.3
#define TDS_TEMP_COEFF  0.02

// ============================================================
// GLOBALS
// ============================================================

OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

unsigned long lastReadTime = 0;
float lastTempC = 25.0;

// Debug/raw values — populated by read functions, sent in payload
float dbg_ph_raw = 0;
float dbg_ph_voltage = 0;
float dbg_ph_before_offset = 0;
float dbg_tds_raw = 0;
float dbg_tds_voltage = 0;
float dbg_tds_compensated_voltage = 0;
float dbg_temp_raw_c = 0;
int   dbg_wifi_reconnects = 0;
int   dbg_post_failures = 0;
int   dbg_reading_count = 0;
unsigned long dbg_heap_free = 0;

// ============================================================
// SETUP
// ============================================================

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n=============================");
    Serial.println("  Media Luna Sensor Hub v2");
    Serial.println("=============================\n");

    tempSensor.begin();
    int deviceCount = tempSensor.getDeviceCount();
    Serial.printf("[temp] Found %d DS18B20 sensor(s)\n", deviceCount);
    if (deviceCount == 0) {
        Serial.println("[temp] WARNING: No DS18B20 found!");
    }

    analogReadResolution(12);
    analogSetPinAttenuation(PH_PIN, ADC_11db);
    analogSetPinAttenuation(TDS_PIN, ADC_11db);

    connectWiFi();

    Serial.println("\n[ready] Sensor hub running. First reading in 5 seconds...\n");
    delay(5000);
}

// ============================================================
// MAIN LOOP
// ============================================================

void loop() {
    unsigned long now = millis();
    
    if (now - lastReadTime >= READ_INTERVAL || lastReadTime == 0) {
        lastReadTime = now;
        dbg_reading_count++;
        dbg_heap_free = ESP.getFreeHeap();

        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[wifi] Connection lost, reconnecting...");
            dbg_wifi_reconnects++;
            connectWiFi();
        }

        float tempC = readTemperature();
        float tempF = tempC * 9.0 / 5.0 + 32.0;
        float ph    = readPH(tempC);
        float tds   = readTDS(tempC);

        lastTempC = tempC;

        Serial.println("--- READING ---");
        Serial.printf("  Temp:  %.2f°C / %.2f°F\n", tempC, tempF);
        Serial.printf("  pH:    %.2f\n", ph);
        Serial.printf("  TDS:   %.0f ppm\n", tds);
        Serial.printf("  Heap:  %lu bytes free\n", dbg_heap_free);

        postData(tempC, tempF, ph, tds);
        
        Serial.printf("  Next reading in %lu seconds\n\n", READ_INTERVAL / 1000);
    }
}

// ============================================================
// SENSOR READING FUNCTIONS
// ============================================================

float readTemperature() {
    tempSensor.requestTemperatures();
    float tempC = tempSensor.getTempCByIndex(0);
    
    if (tempC == DEVICE_DISCONNECTED_C || tempC == -127.0) {
        Serial.println("[temp] ERROR: Sensor disconnected. Using last known value.");
        dbg_temp_raw_c = -127.0;
        return lastTempC;
    }

    dbg_temp_raw_c = tempC;
    return tempC;
}

float readPH(float tempC) {
    long total = 0;
    int samples = 20;
    int minRaw = 4095, maxRaw = 0;
    
    for (int i = 0; i < samples; i++) {
        int reading = analogRead(PH_PIN);
        total += reading;
        if (reading < minRaw) minRaw = reading;
        if (reading > maxRaw) maxRaw = reading;
        delay(10);
    }
    
    float avgRaw = (float)total / samples;
    float voltage = avgRaw * 3.3 / 4095.0;
    
    dbg_ph_raw = avgRaw;
    dbg_ph_voltage = voltage;
    
    float slope = (7.0 - 4.0) / (PH_NEUTRAL_V - PH_ACID_V);
    float ph = 7.0 + (PH_NEUTRAL_V - voltage) * slope;
    
    // Temperature compensation
    ph += (tempC - 25.0) * 0.003;
    
    dbg_ph_before_offset = ph;
    
    // API kit calibration offset
    ph += PH_OFFSET;
    
    if (ph < 0) ph = 0;
    if (ph > 14) ph = 14;
    
    Serial.printf("  [pH] raw=%.0f (±%d) voltage=%.4fV  pre_offset=%.2f  final=%.2f\n", 
                  avgRaw, (maxRaw - minRaw), voltage, dbg_ph_before_offset, ph);
    return ph;
}

float readTDS(float tempC) {
    long total = 0;
    int samples = 20;
    int minRaw = 4095, maxRaw = 0;
    
    for (int i = 0; i < samples; i++) {
        int reading = analogRead(TDS_PIN);
        total += reading;
        if (reading < minRaw) minRaw = reading;
        if (reading > maxRaw) maxRaw = reading;
        delay(10);
    }
    
    float avgRaw = (float)total / samples;
    float voltage = avgRaw * TDS_VREF / 4095.0;
    
    float compensationCoefficient = 1.0 + TDS_TEMP_COEFF * (tempC - 25.0);
    float compensatedVoltage = voltage / compensationCoefficient;
    
    dbg_tds_raw = avgRaw;
    dbg_tds_voltage = voltage;
    dbg_tds_compensated_voltage = compensatedVoltage;
    
    float tds = (133.42 * compensatedVoltage * compensatedVoltage * compensatedVoltage
               - 255.86 * compensatedVoltage * compensatedVoltage
               + 857.39 * compensatedVoltage) * 0.5;
    
    if (tds < 0) tds = 0;
    
    Serial.printf("  [TDS] raw=%.0f (±%d) voltage=%.4fV  comp_v=%.4fV  tds=%.0fppm\n", 
                  avgRaw, (maxRaw - minRaw), voltage, compensatedVoltage, tds);
    return tds;
}

// ============================================================
// NETWORKING
// ============================================================

void connectWiFi() {
    Serial.printf("[wifi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[wifi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[wifi] Server target: %s\n", SERVER_URL);
    } else {
        Serial.println("\n[wifi] FAILED to connect. Will retry on next reading.");
    }
}

void postData(float tempC, float tempF, float ph, float tds) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[post] Skipping — WiFi not connected");
        dbg_post_failures++;
        return;
    }

    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    // === AGENT-READY PAYLOAD ===
    // Top-level: calibrated values the agent acts on
    // "debug": raw sensor data for drift detection & self-calibration
    // "system": ESP32 health metrics
    // "calibration": current params so agent knows what's applied
    
    String p = "{";
    
    // --- Calibrated sensor values (agent acts on these) ---
    p += "\"temp_c\":" + String(tempC, 2) + ",";
    p += "\"temp_f\":" + String(tempF, 2) + ",";
    p += "\"ph\":" + String(ph, 2) + ",";
    p += "\"tds_ppm\":" + String(tds, 0) + ",";
    
    // --- Raw debug data (agent uses for drift detection) ---
    p += "\"debug\":{";
    p += "\"temp_raw_c\":" + String(dbg_temp_raw_c, 2) + ",";
    p += "\"ph_raw_adc\":" + String(dbg_ph_raw, 0) + ",";
    p += "\"ph_voltage\":" + String(dbg_ph_voltage, 4) + ",";
    p += "\"ph_before_offset\":" + String(dbg_ph_before_offset, 2) + ",";
    p += "\"tds_raw_adc\":" + String(dbg_tds_raw, 0) + ",";
    p += "\"tds_voltage\":" + String(dbg_tds_voltage, 4) + ",";
    p += "\"tds_comp_voltage\":" + String(dbg_tds_compensated_voltage, 4);
    p += "},";
    
    // --- System health (agent monitors for failures) ---
    p += "\"system\":{";
    p += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    p += "\"heap_free\":" + String(dbg_heap_free) + ",";
    p += "\"uptime_sec\":" + String(millis() / 1000) + ",";
    p += "\"reading_num\":" + String(dbg_reading_count) + ",";
    p += "\"wifi_reconnects\":" + String(dbg_wifi_reconnects) + ",";
    p += "\"post_failures\":" + String(dbg_post_failures);
    p += "},";
    
    // --- Calibration params (agent knows what's applied) ---
    p += "\"calibration\":{";
    p += "\"ph_neutral_v\":" + String(PH_NEUTRAL_V, 2) + ",";
    p += "\"ph_acid_v\":" + String(PH_ACID_V, 2) + ",";
    p += "\"ph_offset\":" + String(PH_OFFSET, 2) + ",";
    p += "\"tds_vref\":" + String(TDS_VREF, 1) + ",";
    p += "\"tds_temp_coeff\":" + String(TDS_TEMP_COEFF, 2);
    p += "}";
    
    p += "}";

    int httpCode = http.POST(p);

    if (httpCode == 201) {
        Serial.println("  [post] ✓ Data sent to server");
    } else {
        Serial.printf("  [post] ✗ HTTP error: %d\n", httpCode);
        dbg_post_failures++;
        if (httpCode == -1) {
            Serial.println("  [post]   Can't reach server. Check:");
            Serial.println("           1. Flask server running?");
            Serial.println("           2. Correct IP in SERVER_URL?");
            Serial.println("           3. Same WiFi network?");
        }
    }

    http.end();
}
