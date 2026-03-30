/*
 * Media Luna — ESP32 Sensor Hub
 * Reads: DS18B20 temperature, DFRobot pH V2, DFRobot TDS
 * Posts: JSON to Flask endpoint every 15 minutes
 * 
 * WIRING SUMMARY (see build guide for details):
 *   DS18B20 Data  → GPIO 4  (with 4.7kΩ pullup to 3.3V)
 *   pH Signal     → GPIO 34 (ADC1 — CRITICAL: ADC2 fails with WiFi)
 *   TDS Signal    → GPIO 35 (ADC1)
 *   
 * LIBRARIES NEEDED (install via Arduino IDE Library Manager):
 *   - OneWire (by Jim Studt)
 *   - DallasTemperature (by Miles Burton)
 *   - WiFi (built into ESP32 board package)
 *   - HTTPClient (built into ESP32 board package)
 *
 * BOARD SETUP:
 *   Arduino IDE → Boards Manager → search "esp32" → install "ESP32 by Espressif"
 *   Select board: "ESP32 Dev Module"
 *   Upload speed: 115200
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ============================================================
// CONFIG — EDIT THESE
// ============================================================

// WiFi credentials
const char* WIFI_SSID     = "Shroomies";
const char* WIFI_PASSWORD  = "AhnTheSpectrum69";

// Flask server URL — find your laptop IP with: ifconfig (mac) or ipconfig (windows)
// Example: "http://192.168.1.42:5000/api/sensors"
const char* SERVER_URL = "http://192.168.12.12:5001/api/sensors";

// Reading interval (milliseconds). 900000 = 15 min. Use 30000 (30s) for testing.
const unsigned long READ_INTERVAL = 30000;  // START WITH 30s FOR TESTING, change to 900000 later

// ============================================================
// PIN ASSIGNMENTS — ALL ADC1 PINS (ADC2 BROKEN WITH WIFI)
// ============================================================

#define DS18B20_PIN  4     // Digital — any GPIO works
#define PH_PIN       34    // Analog — MUST be ADC1 (32-39)
#define TDS_PIN      35    // Analog — MUST be ADC1 (32-39)

// ============================================================
// SENSOR SETUP
// ============================================================

OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

// pH calibration values (DFRobot V2 defaults)
// Calibrate later: dip probe in pH 7.0 buffer, note voltage. Dip in pH 4.0, note voltage.
// Then adjust these values.
#define PH_OFFSET       0.00    // Adjust after calibration
#define PH_NEUTRAL_V    1.37     // Voltage at pH 7.0 (typical for DFRobot V2)
#define PH_ACID_V       1.88     // Voltage at pH 4.0 (typical)

// TDS calibration
#define TDS_VREF        3.3     // ESP32 ADC reference voltage
#define TDS_TEMP_COEFF  0.02    // Temperature compensation coefficient

// ============================================================
// GLOBALS
// ============================================================

unsigned long lastReadTime = 0;
float lastTempC = 25.0;  // Default for TDS temp compensation before first reading

// ============================================================
// SETUP
// ============================================================

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n=============================");
    Serial.println("  Media Luna Sensor Hub v1");
    Serial.println("=============================\n");

    // Initialize temperature sensor
    tempSensor.begin();
    int deviceCount = tempSensor.getDeviceCount();
    Serial.printf("[temp] Found %d DS18B20 sensor(s)\n", deviceCount);
    if (deviceCount == 0) {
        Serial.println("[temp] WARNING: No DS18B20 found! Check wiring:");
        Serial.println("       Data → GPIO 4, 4.7kΩ pullup to 3.3V");
    }

    // Configure ADC
    analogReadResolution(12);  // 12-bit: 0-4095
    // ADC attenuation for full 0-3.3V range
    analogSetPinAttenuation(PH_PIN, ADC_11db);
    analogSetPinAttenuation(TDS_PIN, ADC_11db);

    // Connect to WiFi
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

        // Reconnect WiFi if dropped
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[wifi] Connection lost, reconnecting...");
            connectWiFi();
        }

        // --- Read all sensors ---
        float tempC = readTemperature();
        float tempF = tempC * 9.0 / 5.0 + 32.0;
        float ph    = readPH(tempC);
        float tds   = readTDS(tempC);

        // Store temp for TDS compensation
        lastTempC = tempC;

        // --- Print to serial ---
        Serial.println("--- READING ---");
        Serial.printf("  Temp:  %.2f°C / %.2f°F\n", tempC, tempF);
        Serial.printf("  pH:    %.2f\n", ph);
        Serial.printf("  TDS:   %.0f ppm\n", tds);

        // --- POST to server ---
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
        return lastTempC;
    }
    return tempC;
}

float readPH(float tempC) {
    // Average multiple readings to reduce noise (DFRobot recommends this)
    long total = 0;
    int samples = 20;
    
    for (int i = 0; i < samples; i++) {
        total += analogRead(PH_PIN);
        delay(10);
    }
    
    float avgRaw = (float)total / samples;
    float voltage = avgRaw * 3.3 / 4095.0;
    
    // Linear conversion: DFRobot V2 outputs ~1.5V at pH 7, ~2.0V at pH 4
    // pH = 7.0 + ((PH_NEUTRAL_V - voltage) / ((PH_ACID_V - PH_NEUTRAL_V) / (7.0 - 4.0)))
    // Simplified: slope from two calibration points
    float slope = (7.0 - 4.0) / (PH_NEUTRAL_V - PH_ACID_V);
    float ph = 7.0 + (PH_NEUTRAL_V - voltage) * slope + PH_OFFSET;
    
    // Basic temperature compensation (~0.03 pH per °C deviation from 25°C)
    ph += (tempC - 25.0) * 0.003;
    
    // Sanity clamp
    if (ph < 0) ph = 0;
    if (ph > 14) ph = 14;
    
    Serial.printf("  [pH debug] raw=%0.f  voltage=%.3fV  ph=%.2f\n", avgRaw, voltage, ph);
    return ph;
}

float readTDS(float tempC) {
    // Average readings
    long total = 0;
    int samples = 20;
    
    for (int i = 0; i < samples; i++) {
        total += analogRead(TDS_PIN);
        delay(10);
    }
    
    float avgRaw = (float)total / samples;
    float voltage = avgRaw * TDS_VREF / 4095.0;
    
    // Temperature compensation (DFRobot formula)
    float compensationCoefficient = 1.0 + TDS_TEMP_COEFF * (tempC - 25.0);
    float compensatedVoltage = voltage / compensationCoefficient;
    
    // TDS conversion (DFRobot formula from their wiki)
    float tds = (133.42 * compensatedVoltage * compensatedVoltage * compensatedVoltage
               - 255.86 * compensatedVoltage * compensatedVoltage
               + 857.39 * compensatedVoltage) * 0.5;
    
    if (tds < 0) tds = 0;
    
    Serial.printf("  [TDS debug] raw=%.0f  voltage=%.3fV  tds=%.0fppm\n", avgRaw, voltage, tds);
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
        return;
    }

    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    // Build JSON payload
    String payload = "{";
    payload += "\"temp_c\":" + String(tempC, 2) + ",";
    payload += "\"temp_f\":" + String(tempF, 2) + ",";
    payload += "\"ph\":" + String(ph, 2) + ",";
    payload += "\"tds_ppm\":" + String(tds, 0) + ",";
    payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    payload += "\"uptime_sec\":" + String(millis() / 1000);
    payload += "}";

    int httpCode = http.POST(payload);

    if (httpCode == 201) {
        Serial.println("  [post] ✓ Data sent to server");
    } else {
        Serial.printf("  [post] ✗ HTTP error: %d\n", httpCode);
        if (httpCode == -1) {
            Serial.println("  [post]   Can't reach server. Check:");
            Serial.println("           1. Flask server running?");
            Serial.println("           2. Correct IP in SERVER_URL?");
            Serial.println("           3. Same WiFi network?");
        }
    }

    http.end();
}
