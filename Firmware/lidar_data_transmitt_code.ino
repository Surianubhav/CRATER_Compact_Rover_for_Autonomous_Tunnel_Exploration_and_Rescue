#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>

// =====================================================
// WIFI
// =====================================================

const char* WIFI_SSID = "surilidar";
const char* WIFI_PASSWORD = "11111111";

IPAddress laptopIP(10, 42, 0, 1);

const uint16_t UDP_PORT = 4211;
const uint16_t CONTROL_PORT = 4210;

WiFiUDP udp;
WiFiUDP controlUdp;


// =====================================================
// AS5600
// =====================================================

#define AS5600_ADDR 0x36

#define SDA_PIN 21
#define SCL_PIN 22


// =====================================================
// TF-LUNA
// =====================================================

#define TF_RX 16
#define TF_TX 17

HardwareSerial TFSerial(2);

#define TF_LUNA_BAUD 115200
#define TF_LUNA_RATE 250


// =====================================================
// MAPPING TIMING
// =====================================================

volatile bool mappingStarted = false;

uint32_t mappingStartMicros = 0;
uint32_t sequenceNumber = 0;


// =====================================================
// STATISTICS
// =====================================================

uint32_t packetCount = 0;
uint32_t checksumErrors = 0;
uint32_t invalidFrames = 0;

uint32_t lastStatsMillis = 0;
uint32_t lastStatsPacketCount = 0;


// =====================================================
// AS5600
// =====================================================

int16_t readAS5600() {

  Wire.beginTransmission(AS5600_ADDR);

  Wire.write(0x0C);

  if (Wire.endTransmission(false) != 0) {
    return -1;
  }

  uint8_t received =
    Wire.requestFrom(
      AS5600_ADDR,
      (uint8_t)2
    );

  if (received < 2) {
    return -1;
  }

  uint8_t highByte = Wire.read();
  uint8_t lowByte = Wire.read();

  uint16_t rawAngle =
    ((uint16_t)highByte << 8) |
    lowByte;

  rawAngle &= 0x0FFF;

  return (int16_t)rawAngle;
}


// =====================================================
// TF-LUNA COMMAND
// =====================================================
//
// Official 250 Hz command:
//
// 5A 06 03 FA 00 00
//
// Save settings:
//
// 5A 04 11 6F
//
// =====================================================

void configureTFLuna() {

  Serial.println();
  Serial.println("Configuring TF-Luna...");

  // Stop/clear any existing serial data
  while (TFSerial.available()) {
    TFSerial.read();
  }

  // ---------------------------------------------------
  // Set output frequency = 250 Hz
  // ---------------------------------------------------

  uint8_t frequencyCommand[6] = {
    0x5A,
    0x06,
    0x03,
    0xFA,
    0x00,
    0x00
  };

  TFSerial.write(
    frequencyCommand,
    sizeof(frequencyCommand)
  );

  TFSerial.flush();

  delay(100);

  // ---------------------------------------------------
  // Set standard 9-byte centimeter output format
  // ---------------------------------------------------

  uint8_t formatCommand[5] = {
    0x5A,
    0x05,
    0x05,
    0x01,
    0x65
  };

  TFSerial.write(
    formatCommand,
    sizeof(formatCommand)
  );

  TFSerial.flush();

  delay(100);

  // ---------------------------------------------------
  // Save settings
  // ---------------------------------------------------

  uint8_t saveCommand[4] = {
    0x5A,
    0x04,
    0x11,
    0x6F
  };

  TFSerial.write(
    saveCommand,
    sizeof(saveCommand)
  );

  TFSerial.flush();

  delay(100);

  // Clear command responses
  while (TFSerial.available()) {
    TFSerial.read();
  }

  Serial.println("TF-Luna configured for 250 Hz.");
}


// =====================================================
// READ TF-LUNA
// =====================================================

bool readTFLuna(uint16_t &distance) {

  static uint8_t buffer[9];

  while (TFSerial.available() >= 2) {

    // -------------------------------------------------
    // Find first 0x59
    // -------------------------------------------------

    if (TFSerial.peek() != 0x59) {

      TFSerial.read();

      invalidFrames++;

      continue;
    }

    // -------------------------------------------------
    // Wait for complete frame
    // -------------------------------------------------

    if (TFSerial.available() < 9) {
      return false;
    }

    // -------------------------------------------------
    // Read frame
    // -------------------------------------------------

    for (int i = 0; i < 9; i++) {
      buffer[i] = TFSerial.read();
    }

    // -------------------------------------------------
    // Header
    // -------------------------------------------------

    if (buffer[0] != 0x59 ||
        buffer[1] != 0x59) {

      invalidFrames++;

      continue;
    }

    // -------------------------------------------------
    // Checksum
    // -------------------------------------------------

    uint8_t checksum = 0;

    for (int i = 0; i < 8; i++) {
      checksum += buffer[i];
    }

    if (checksum != buffer[8]) {

      checksumErrors++;

      continue;
    }

    // -------------------------------------------------
    // Distance
    // -------------------------------------------------

    distance =
      buffer[2] |
      ((uint16_t)buffer[3] << 8);

    return true;
  }

  return false;
}


// =====================================================
// SEND LIDAR PACKET
// =====================================================

void sendLidarPacket(
  uint32_t timestamp,
  uint32_t sequence,
  uint16_t angleRaw,
  uint16_t distance
) {

  udp.beginPacket(
    laptopIP,
    UDP_PORT
  );

  udp.print("{");

  udp.print("\"device\":\"lidar\"");

  udp.print(",\"seq\":");
  udp.print(sequence);

  udp.print(",\"t\":");
  udp.print(timestamp);

  udp.print(",\"angleRaw\":");
  udp.print(angleRaw);

  udp.print(",\"angle\":");
  udp.print(
    angleRaw * 360.0 / 4096.0,
    3
  );

  udp.print(",\"distance\":");
  udp.print(distance);

  udp.print("}");

  udp.endPacket();
}


// =====================================================
// SEND STATUS
// =====================================================

void sendStatus() {

  udp.beginPacket(
    laptopIP,
    UDP_PORT
  );

  udp.print("{");

  udp.print("\"device\":\"lidar_status\"");

  udp.print(",\"ready\":true");

  udp.print(",\"started\":");
  udp.print(
    mappingStarted ? "true" : "false"
  );

  udp.print(",\"seq\":");
  udp.print(sequenceNumber);

  udp.print("}");

  udp.endPacket();
}


// =====================================================
// HANDLE CONTROL COMMANDS
// =====================================================
//
// Laptop sends:
// START
//
// This resets:
// sequence = 0
// timestamp = 0
//
// Both ESP32s can receive the same START broadcast.
// =====================================================

void handleControl() {

  int packetSize =
    controlUdp.parsePacket();

  if (packetSize <= 0) {
    return;
  }

  char command[32];

  int len =
    controlUdp.read(
      command,
      sizeof(command) - 1
    );

  if (len <= 0) {
    return;
  }

  command[len] = '\0';

  // ---------------------------------------------------
  // START MAPPING
  // ---------------------------------------------------

  if (strcmp(command, "START") == 0) {

    mappingStartMicros = micros();

    sequenceNumber = 0;

    packetCount = 0;

    mappingStarted = true;

    Serial.println();
    Serial.println(">>> MAPPING STARTED <<<");

    sendStatus();
  }

  // ---------------------------------------------------
  // RESET
  // ---------------------------------------------------

  else if (strcmp(command, "RESET") == 0) {

    mappingStarted = false;

    mappingStartMicros = 0;

    sequenceNumber = 0;

    Serial.println();
    Serial.println(">>> MAPPING RESET <<<");

    sendStatus();
  }
}


// =====================================================
// STATISTICS
// =====================================================

void printStatistics() {

  uint32_t now =
    millis();

  if (now - lastStatsMillis < 1000) {
    return;
  }

  uint32_t currentCount =
    packetCount;

  uint32_t rate =
    currentCount -
    lastStatsPacketCount;

  Serial.print("LIDAR: ");
  Serial.print(rate);
  Serial.print(" Hz");

  Serial.print(" | total=");
  Serial.print(currentCount);

  Serial.print(" | checksum=");
  Serial.print(checksumErrors);

  Serial.print(" | invalid=");
  Serial.print(invalidFrames);

  Serial.print(" | mapping=");
  Serial.println(
    mappingStarted ? "ON" : "OFF"
  );

  lastStatsPacketCount =
    currentCount;

  lastStatsMillis =
    now;
}


// =====================================================
// WIFI
// =====================================================

void connectWiFi() {

  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);

  WiFi.setSleep(false);

  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );

  int attempts = 0;

  while (
    WiFi.status() != WL_CONNECTED &&
    attempts < 40
  ) {

    delay(500);

    Serial.print(".");

    attempts++;
  }

  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {

    Serial.println(
      "WIFI CONNECTION FAILED!"
    );

    return;
  }

  Serial.println(
    "WIFI CONNECTED!"
  );

  Serial.print("ESP32 IP: ");
  Serial.println(
    WiFi.localIP()
  );

  udp.begin(UDP_PORT);

  controlUdp.begin(
    CONTROL_PORT
  );

  Serial.print(
    "Data UDP: "
  );

  Serial.println(
    UDP_PORT
  );

  Serial.print(
    "Control UDP: "
  );

  Serial.println(
    CONTROL_PORT
  );
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println();
  Serial.println(
    "===================================="
  );

  Serial.println(
    "      FINAL LIDAR ESP32"
  );

  Serial.println(
    "===================================="
  );

  // ---------------------------------------------------
  // AS5600
  // ---------------------------------------------------

  Wire.begin(
    SDA_PIN,
    SCL_PIN,
    400000
  );

  // ---------------------------------------------------
  // TF-Luna
  // ---------------------------------------------------

  TFSerial.begin(
    TF_LUNA_BAUD,
    SERIAL_8N1,
    TF_RX,
    TF_TX
  );

  delay(200);

  configureTFLuna();

  // ---------------------------------------------------
  // WiFi
  // ---------------------------------------------------

  connectWiFi();

  // ---------------------------------------------------
  // Initial state
  // ---------------------------------------------------

  mappingStarted = false;

  sequenceNumber = 0;

  lastStatsMillis = millis();

  Serial.println();
  Serial.println(
    "LIDAR READY."
  );

  Serial.println(
    "Waiting for START command..."
  );
}


// =====================================================
// LOOP
// =====================================================

void loop() {

  // ---------------------------------------------------
  // Check laptop commands
  // ---------------------------------------------------

  handleControl();

  // ---------------------------------------------------
  // Read all available LiDAR frames
  // ---------------------------------------------------

  while (true) {

    uint16_t distance;

    if (!readTFLuna(distance)) {
      break;
    }

    // -------------------------------------------------
    // Read angle as close as possible to LiDAR sample
    // -------------------------------------------------

    int16_t angleRaw =
      readAS5600();

    if (angleRaw < 0) {
      continue;
    }

    // -------------------------------------------------
    // Ignore measurements before START
    // -------------------------------------------------

    if (!mappingStarted) {
      continue;
    }

    // -------------------------------------------------
    // Timestamp relative to mapping START
    // -------------------------------------------------

    uint32_t timestamp =
      micros() -
      mappingStartMicros;

    // -------------------------------------------------
    // Send
    // -------------------------------------------------

    sendLidarPacket(
      timestamp,
      sequenceNumber,
      (uint16_t)angleRaw,
      distance
    );

    sequenceNumber++;

    packetCount++;
  }

  // ---------------------------------------------------
  // Statistics
  // ---------------------------------------------------

  printStatistics();
}