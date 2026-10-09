/*
  Mine Rescue Rover - Sensor Node (Arduino Nano)
  -----------------------------------------------
  Reads MQ-4, MQ-7, DHT22, BMP180 and sends a single JSON line
  to an ESP32 every SEND_INTERVAL_MS, over a SoftwareSerial link
  on A2/A3 (keeps D0/D1 free for USB programming/debugging).

  Libraries needed (install via Library Manager):
    - "DHT sensor library" by Adafruit  (also needs "Adafruit Unified Sensor")
    - "Adafruit BMP085 Library" (works for BMP180 too)
    - "SoftwareSerial" (bundled with the Arduino IDE, no install needed)

  Wiring to ESP32 (cross the RX/TX, common ground):
    Nano A3 (TX)  ->  ESP32 RX pin
    Nano A2 (RX)  <-  ESP32 TX pin
    Nano GND      ->  ESP32 GND

  D0/D1 are left untouched, so you can upload and monitor over USB
  with the ESP32 connected the whole time - no need to unplug anything.

  DEBUG MODE: this version always sends over espSerial (no more on/off
  flag to forget) AND prints exactly what it sends to the USB Serial
  Monitor too, tagged "TX->ESP:", plus a running heartbeat counter
  so you can confirm the Nano is alive and transmitting even before
  you trust the sensor readings themselves.
*/

#include <DHT.h>
#include <Wire.h>
#include <Adafruit_BMP085.h>
#include <SoftwareSerial.h>

// ---------- Pin / sensor config ----------
#define MQ4_PIN   A0
#define MQ7_PIN   A1
#define DHTPIN    2
#define DHTTYPE   DHT22
#define ESP_RX    A2   // Nano receives here <- ESP32 TX
#define ESP_TX    A3   // Nano transmits here -> ESP32 RX

const unsigned long SEND_INTERVAL_MS = 2000;  // DHT22 needs >=2s between reads

DHT dht(DHTPIN, DHTTYPE);
Adafruit_BMP085 bmp;
SoftwareSerial espSerial(ESP_RX, ESP_TX);  // RX, TX

bool bmpOk = false;
unsigned long lastSend = 0;
unsigned long heartbeat = 0;

void setup() {
  Serial.begin(9600);       // USB - Serial Monitor for testing/debugging
  espSerial.begin(9600);    // link to the ESP32 - always on now, no flag

  dht.begin();

  bmpOk = bmp.begin();      // false if BMP180 not found on I2C (A4/A5)
  if (!bmpOk) {
    Serial.println(F("WARNING: BMP180 not detected on I2C (A4/A5) - check wiring."));
  }

  Serial.println(F("Nano booted. Sending heartbeat + JSON over A2/A3 every 2s."));
}

void loop() {
  unsigned long now = millis();
  if (now - lastSend < SEND_INTERVAL_MS) {
    return;
  }
  lastSend = now;

  // ---------- Read sensors ----------
  int mq4Raw = analogRead(MQ4_PIN);   // raw ADC 0-1023, calibrate later if needed
  int mq7Raw = analogRead(MQ7_PIN);

  float temp = dht.readTemperature();  // NAN if the read failed
  float hum  = dht.readHumidity();

  float pressurePa = 0;
  float altitudeM  = 0;
  if (bmpOk) {
    pressurePa = bmp.readPressure();
    altitudeM  = bmp.readAltitude();
  }

  // ---------- Human-readable debug output (Serial Monitor, 9600 baud) ----------
  Serial.println(F("---- sensor readings ----"));

  Serial.print(F("MQ4 raw:      ")); Serial.println(mq4Raw);
  Serial.print(F("MQ7 raw:      ")); Serial.println(mq7Raw);

  Serial.print(F("DHT22 temp:   "));
  if (isnan(temp)) Serial.println(F("read failed")); else { Serial.print(temp); Serial.println(F(" C")); }

  Serial.print(F("DHT22 hum:    "));
  if (isnan(hum)) Serial.println(F("read failed")); else { Serial.print(hum); Serial.println(F(" %")); }

  Serial.print(F("BMP180:       "));
  if (!bmpOk) {
    Serial.println(F("not detected"));
  } else {
    Serial.print(pressurePa); Serial.print(F(" Pa, alt "));
    Serial.print(altitudeM);  Serial.println(F(" m"));
  }

  heartbeat++;

  // ---------- Build JSON manually (keeps it lightweight, no extra library) ----------
  char json[180];
  snprintf(json, sizeof(json),
    "{\"hb\":%lu,\"mq4\":%d,\"mq7\":%d,\"temp\":%s,\"hum\":%s,\"pressure\":%s,\"alt\":%s,\"bmp_ok\":%s}",
    heartbeat,
    mq4Raw,
    mq7Raw,
    isnan(temp) ? "null" : String(temp, 2).c_str(),
    isnan(hum)  ? "null" : String(hum, 2).c_str(),
    bmpOk ? String(pressurePa, 1).c_str() : "null",
    bmpOk ? String(altitudeM, 2).c_str()  : "null",
    bmpOk ? "true" : "false"
  );

  Serial.print(F("JSON:         "));
  Serial.println(json);       // always visible on the Serial Monitor for testing
  Serial.println();

  espSerial.println(json);    // one JSON object per line -> easy for ESP32 to parse

  // Echo exactly what was just sent to A3, so you can compare byte-for-byte
  // against whatever (if anything) the ESP32's Serial Monitor reports receiving.
  Serial.print(F("TX->ESP: "));
  Serial.println(json);
}
