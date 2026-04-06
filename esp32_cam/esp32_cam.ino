/*
 * Media Luna — ESP32-CAM Snapshot Poster
 * Board: AI Thinker ESP32-CAM
 *
 * Every SNAPSHOT_INTERVAL_MS milliseconds, captures a JPEG frame and POSTs it
 * to the Media Luna sensor server at POST /api/snapshot.
 *
 * Also runs a web server on port 80 for on-demand snapshots:
 *   - GET http://<esp-ip>/ — status page
 *   - GET http://<esp-ip>/capture — trigger immediate snapshot
 *
 * Wiring reminder:
 *   - GPIO0 → GND during flash only; remove jumper before normal operation
 *   - FTDI: GND→GND, 5V→5V, TX→U0R, RX→U0T
 *
 * Upload: Arduino IDE with board "AI Thinker ESP32-CAM"
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

// ── WiFi credentials ──────────────────────────────────────────────────────────
const char* WIFI_SSID = "Shroomies";
const char* WIFI_PASS = "AhnTheSpectrum69";

// ── Server ────────────────────────────────────────────────────────────────────
const char* SERVER_URL = "http://192.168.12.76:5001/api/snapshot";

// ── Interval ──────────────────────────────────────────────────────────────────
// Post a snapshot every 5 minutes. shrimp-vision runs every 2 hours and
// considers any snapshot < 30 min old as "live".
const unsigned long SNAPSHOT_INTERVAL_MS = 5UL * 60UL * 1000UL;

// ── Web server for on-demand capture ──────────────────────────────────────────
WebServer server(80);

// ── AI Thinker ESP32-CAM pin map ──────────────────────────────────────────────
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22


void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // PSRAM present on AI Thinker — use higher res
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;   // 640×480, good for tank view
    config.jpeg_quality = 12;              // 0=best, 63=worst
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_QVGA;  // 320×240 fallback
    config.jpeg_quality = 15;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: 0x%x — rebooting\n", err);
    delay(1000);
    ESP.restart();
  }
  Serial.println("[cam] camera ready");
}


void connectWiFi() {
  Serial.printf("[wifi] connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] connected — IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[wifi] failed — rebooting");
    delay(1000);
    ESP.restart();
  }
}


bool postSnapshot() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[snap] frame capture failed");
    return false;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[snap] WiFi lost — reconnecting");
    connectWiFi();
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "image/jpeg");
  http.setTimeout(10000);

  int code = http.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (code == 201) {
    Serial.printf("[snap] posted %u bytes → %d\n", fb->len, code);
    http.end();
    return true;
  } else {
    Serial.printf("[snap] POST failed: %d\n", code);
    http.end();
    return false;
  }
}


void handleCapture() {
  Serial.println("[web] capture request received");
  bool success = postSnapshot();
  if (success) {
    server.send(200, "text/plain", "Snapshot captured and posted");
  } else {
    server.send(500, "text/plain", "Snapshot failed");
  }
}

void handleRoot() {
  String html = "<html><body><h1>Media Luna ESP32-CAM</h1>";
  html += "<p>Status: Online</p>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p><a href='/capture'>Trigger Snapshot</a></p>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}


void setup() {
  Serial.begin(115200);
  Serial.println("\n[boot] Media Luna ESP32-CAM");

  initCamera();
  connectWiFi();

  // Start web server for on-demand captures
  server.on("/", handleRoot);
  server.on("/capture", handleCapture);
  server.begin();
  Serial.printf("[web] server started at http://%s/\n", WiFi.localIP().toString().c_str());

  // Post immediately on boot so the server has a snapshot right away
  postSnapshot();
}


void loop() {
  server.handleClient();  // Handle web requests

  static unsigned long lastPost = 0;
  unsigned long now = millis();

  if (now - lastPost >= SNAPSHOT_INTERVAL_MS) {
    postSnapshot();
    lastPost = now;
  }

  delay(100);  // Reduced delay for more responsive web server
}
