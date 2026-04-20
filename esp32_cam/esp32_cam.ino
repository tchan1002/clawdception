/*
 * Media Luna — ESP32-CAM
 * Board: AI Thinker ESP32-CAM
 *
 * Endpoints:
 *   GET /            — status page
 *   GET /snapshot    — capture and return single JPEG (Pi pulls on demand)
 *   GET /livestream  — continuous MJPEG stream (~10fps, not saved)
 *
 * Wiring reminder:
 *   - GPIO0 → GND during flash only; remove jumper before normal operation
 *   - FTDI: GND→GND, 5V→5V, TX→U0R, RX→U0T
 *
 * Upload: Arduino IDE with board "AI Thinker ESP32-CAM"
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ── WiFi credentials ──────────────────────────────────────────────────────────
const char* WIFI_SSID = "Shroomies";
const char* WIFI_PASS = "AhnTheSpectrum69";

// ── Web server ────────────────────────────────────────────────────────────────
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


void handleSnapshot() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    server.send(503, "text/plain", "Camera capture failed");
    Serial.println("[snap] frame capture failed");
    return;
  }
  server.sendHeader("Content-Disposition", "inline; filename=snapshot.jpg");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  Serial.printf("[snap] served %u bytes\n", fb->len);
  esp_camera_fb_return(fb);
}


void handleLivestream() {
  WiFiClient client = server.client();

  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Cache-Control: no-cache");
  client.println("Connection: close");
  client.println();

  Serial.println("[stream] client connected");
  while (client.connected()) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) break;

    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);

    delay(100);  // ~10fps
  }
  Serial.println("[stream] client disconnected");
}


void handleRoot() {
  String html = "<html><body><h1>Media Luna ESP32-CAM</h1>";
  html += "<p>Status: Online</p>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p><a href='/snapshot'>Capture Snapshot</a></p>";
  html += "<p><a href='/livestream'>View Livestream</a></p>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}


void setup() {
  Serial.begin(115200);
  Serial.println("\n[boot] Media Luna ESP32-CAM");

  initCamera();
  connectWiFi();

  server.on("/", handleRoot);
  server.on("/snapshot", handleSnapshot);
  server.on("/livestream", handleLivestream);
  server.begin();
  Serial.printf("[web] server started at http://%s/\n", WiFi.localIP().toString().c_str());
}


void loop() {
  server.handleClient();
  delay(10);
}
