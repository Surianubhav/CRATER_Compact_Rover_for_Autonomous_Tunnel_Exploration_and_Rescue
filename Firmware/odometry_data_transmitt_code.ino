#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>

// =====================================================
// WIFI
// =====================================================

const char* WIFI_SSID = "surilidar";
const char* WIFI_PASSWORD = "11111111";

IPAddress laptopIP(10, 42, 0, 1);

const uint16_t UDP_PORT = 4212;
const uint16_t CONTROL_PORT = 4210;

WiFiUDP udp;
WiFiUDP controlUdp;


// =====================================================
// I2C BUS 1
// LEFT AS5600 + MPU6500
// =====================================================

TwoWire I2C_1 = TwoWire(0);

#define SDA1 18
#define SCL1 19


// =====================================================
// I2C BUS 2
// RIGHT AS5600
// =====================================================

TwoWire I2C_2 = TwoWire(1);

#define SDA2 21
#define SCL2 22


// =====================================================
// ADDRESSES
// =====================================================

#define AS5600_ADDR 0x36
#define MPU6500_ADDR 0x68


// =====================================================
// LIDAR ROTATION MOTOR
// =====================================================

#define MOTOR_PWM_PIN 23

#define PWM_CHANNEL 0
#define PWM_FREQUENCY 20000
#define PWM_RESOLUTION 8

#define MOTOR_PWM_50 128


// =====================================================
// ODOMETRY RATE
// =====================================================

#define ODOM_RATE_HZ 100

const uint32_t ODOM_PERIOD_US =
  1000000UL / ODOM_RATE_HZ;


// =====================================================
// ENCODER CALIBRATION
// =====================================================
//
// Your measured calibration:
//
// LEFT  = 0.147699 m / motor revolution
// RIGHT = 0.148708 m / motor revolution
//
// These are NOT wheel-radius calculations.
// Encoders are mounted on motor shafts.
//
// Direction:
//
// LEFT  forward = negative
// RIGHT forward = positive
// =====================================================

const float LEFT_METERS_PER_REV =
  0.147699f;

const float RIGHT_METERS_PER_REV =
  0.148708f;

const float LEFT_DIRECTION =
  -1.0f;

const float RIGHT_DIRECTION =
  +1.0f;


// =====================================================
// TRACK WIDTH
// =====================================================

const float TRACK_WIDTH_M =
  0.180f;


// =====================================================
// MPU6500 SCALE
// =====================================================

const float ACCEL_LSB_PER_G =
  16384.0f;

const float GYRO_LSB_PER_DPS =
  131.0f;


// =====================================================
// GYRO FILTER
// =====================================================
//
// Cutoff ~15 Hz.
//
// Odometry runs at 100 Hz.
//
// This is intentionally not extremely aggressive.
// We want to remove high-frequency vibration while
// keeping actual rover turns responsive.
// =====================================================

const float GYRO_CUTOFF_HZ =
  15.0f;


// =====================================================
// ACCEL FILTER
// =====================================================
//
// Used only for cleaner diagnostics / slip analysis.
// NOT integrated for position.
// =====================================================

const float ACCEL_CUTOFF_HZ =
  5.0f;


// =====================================================
// SENSOR VALIDITY
// =====================================================

bool leftEncoderOK = false;
bool rightEncoderOK = false;
bool imuOK = false;


// =====================================================
// MAPPING TIMING
// =====================================================

volatile bool mappingStarted = false;

uint32_t mappingStartMicros = 0;
uint32_t sequenceNumber = 0;


// =====================================================
// ENCODER STATE
// =====================================================

struct EncoderState {

  uint16_t previousRaw;

  int32_t unwrappedRaw;

  bool initialized;

  float revolutions;
};


EncoderState leftEncoder = {
  0,
  0,
  false,
  0.0f
};

EncoderState rightEncoder = {
  0,
  0,
  false,
  0.0f
};


// =====================================================
// IMU FILTER STATE
// =====================================================

float gyroBiasX = 0.0f;
float gyroBiasY = 0.0f;
float gyroBiasZ = 0.0f;

float filteredGx = 0.0f;
float filteredGy = 0.0f;
float filteredGz = 0.0f;

float filteredAx = 0.0f;
float filteredAy = 0.0f;
float filteredAz = 0.0f;

bool filterInitialized = false;


// =====================================================
// STATISTICS
// =====================================================

uint32_t packetCount = 0;

uint32_t leftEncoderErrors = 0;
uint32_t rightEncoderErrors = 0;
uint32_t imuErrors = 0;

uint32_t lastStatsMillis = 0;
uint32_t lastStatsPacketCount = 0;


// =====================================================
// MOTOR
// =====================================================

void setupMotor() {

  Serial.println();
  Serial.println(
    "Initializing LiDAR rotation motor..."
  );

  ledcSetup(
    PWM_CHANNEL,
    PWM_FREQUENCY,
    PWM_RESOLUTION
  );

  ledcAttachPin(
    MOTOR_PWM_PIN,
    PWM_CHANNEL
  );

  ledcWrite(
    PWM_CHANNEL,
    MOTOR_PWM_50
  );

  Serial.println(
    "LiDAR motor = 50% PWM"
  );
}


// =====================================================
// AS5600 RAW READ
// =====================================================

uint16_t readAS5600(
  TwoWire &bus,
  bool &ok
) {

  bus.beginTransmission(
    AS5600_ADDR
  );

  bus.write(0x0C);

  if (
    bus.endTransmission(false) != 0
  ) {

    ok = false;

    return 0;
  }

  uint8_t received =
    bus.requestFrom(
      AS5600_ADDR,
      (uint8_t)2
    );

  if (received < 2) {

    ok = false;

    return 0;
  }

  uint8_t highByte =
    bus.read();

  uint8_t lowByte =
    bus.read();

  uint16_t rawAngle =
    ((uint16_t)highByte << 8) |
    lowByte;

  ok = true;

  return rawAngle & 0x0FFF;
}


// =====================================================
// ENCODER UNWRAP
// =====================================================
//
// AS5600 range:
//
// 0 ... 4095
//
// When:
//
// 4095 → 0
//
// that is NOT a full backwards revolution.
//
// We detect the wrap and maintain a continuous count.
// =====================================================

float updateEncoder(
  EncoderState &state,
  uint16_t raw
) {

  if (!state.initialized) {

    state.previousRaw =
      raw;

    state.unwrappedRaw =
      raw;

    state.revolutions =
      0.0f;

    state.initialized =
      true;

    return state.revolutions;
  }

  int32_t delta =
    (int32_t)raw -
    (int32_t)state.previousRaw;

  // ---------------------------------------------------
  // Forward wrap:
  //
  // 4095 -> 0
  // ---------------------------------------------------

  if (delta > 2048) {
    delta -= 4096;
  }

  // ---------------------------------------------------
  // Reverse wrap:
  //
  // 0 -> 4095
  // ---------------------------------------------------

  else if (delta < -2048) {
    delta += 4096;
  }

  state.unwrappedRaw +=
    delta;

  state.previousRaw =
    raw;

  state.revolutions =
    (float)state.unwrappedRaw /
    4096.0f;

  return state.revolutions;
}


// =====================================================
// MPU REGISTER WRITE
// =====================================================

bool writeMPU(
  uint8_t reg,
  uint8_t value
) {

  I2C_1.beginTransmission(
    MPU6500_ADDR
  );

  I2C_1.write(reg);
  I2C_1.write(value);

  return (
    I2C_1.endTransmission() == 0
  );
}


// =====================================================
// MPU REGISTER READ
// =====================================================

uint8_t readMPURegister(
  uint8_t reg
) {

  I2C_1.beginTransmission(
    MPU6500_ADDR
  );

  I2C_1.write(reg);

  if (
    I2C_1.endTransmission(false) != 0
  ) {

    return 0xFF;
  }

  uint8_t received =
    I2C_1.requestFrom(
      MPU6500_ADDR,
      (uint8_t)1
    );

  if (received) {
    return I2C_1.read();
  }

  return 0xFF;
}


// =====================================================
// MPU INIT
// =====================================================

bool initMPU6500() {

  Serial.println();
  Serial.println(
    "Initializing MPU6500..."
  );

  uint8_t whoAmI =
    readMPURegister(0x75);

  Serial.print(
    "WHO_AM_I = 0x"
  );

  Serial.println(
    whoAmI,
    HEX
  );

  if (
    whoAmI != 0x70 &&
    whoAmI != 0x71 &&
    whoAmI != 0x73
  ) {

    Serial.println(
      "MPU6500 NOT DETECTED!"
    );

    return false;
  }

  // Wake
  writeMPU(
    0x6B,
    0x00
  );

  delay(100);

  // Accelerometer ±2g
  writeMPU(
    0x1C,
    0x00
  );

  // Gyroscope ±250 deg/s
  writeMPU(
    0x1B,
    0x00
  );

  // DLPF
  writeMPU(
    0x1A,
    0x03
  );

  Serial.println(
    "MPU6500 OK"
  );

  return true;
}


// =====================================================
// READ MPU6500
// =====================================================

bool readMPU(
  int16_t &ax,
  int16_t &ay,
  int16_t &az,
  int16_t &gx,
  int16_t &gy,
  int16_t &gz
) {

  I2C_1.beginTransmission(
    MPU6500_ADDR
  );

  I2C_1.write(0x3B);

  if (
    I2C_1.endTransmission(false) != 0
  ) {

    return false;
  }

  uint8_t received =
    I2C_1.requestFrom(
      MPU6500_ADDR,
      (uint8_t)14
    );

  if (received < 14) {
    return false;
  }

  ax =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  ay =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  az =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  // Temperature
  I2C_1.read();
  I2C_1.read();

  gx =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  gy =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  gz =
    ((int16_t)I2C_1.read() << 8) |
    I2C_1.read();

  return true;
}


// =====================================================
// FILTER COEFFICIENT
// =====================================================

float calculateAlpha(
  float cutoffHz,
  float dt
) {

  float RC =
    1.0f /
    (2.0f * PI * cutoffHz);

  return dt /
    (RC + dt);
}


// =====================================================
// GYRO FILTER
// =====================================================

void filterGyro(
  float gx,
  float gy,
  float gz,
  float dt
) {

  float alpha =
    calculateAlpha(
      GYRO_CUTOFF_HZ,
      dt
    );

  // ---------------------------------------------------
  // Bias removal FIRST
  // ---------------------------------------------------

  gx -= gyroBiasX;
  gy -= gyroBiasY;
  gz -= gyroBiasZ;

  // ---------------------------------------------------
  // Low pass
  // ---------------------------------------------------

  if (!filterInitialized) {

    filteredGx = gx;
    filteredGy = gy;
    filteredGz = gz;

    return;
  }

  filteredGx =
    filteredGx +
    alpha * (gx - filteredGx);

  filteredGy =
    filteredGy +
    alpha * (gy - filteredGy);

  filteredGz =
    filteredGz +
    alpha * (gz - filteredGz);
}


// =====================================================
// ACCEL FILTER
// =====================================================

void filterAccel(
  float ax,
  float ay,
  float az,
  float dt
) {

  float alpha =
    calculateAlpha(
      ACCEL_CUTOFF_HZ,
      dt
    );

  if (!filterInitialized) {

    filteredAx = ax;
    filteredAy = ay;
    filteredAz = az;

    return;
  }

  filteredAx =
    filteredAx +
    alpha * (ax - filteredAx);

  filteredAy =
    filteredAy +
    alpha * (ay - filteredAy);

  filteredAz =
    filteredAz +
    alpha * (az - filteredAz);
}


// =====================================================
// GYRO BIAS CALIBRATION
// =====================================================
//
// Rover MUST remain completely stationary.
//
// We collect samples for 3 seconds.
// =====================================================

bool calibrateGyro() {

  Serial.println();
  Serial.println(
    "===================================="
  );

  Serial.println(
    "GYRO CALIBRATION"
  );

  Serial.println(
    "KEEP ROVER COMPLETELY STILL"
  );

  Serial.println(
    "Calibrating for 3 seconds..."
  );

  const uint32_t duration =
    3000000UL;

  uint32_t start =
    micros();

  int64_t sumX = 0;
  int64_t sumY = 0;
  int64_t sumZ = 0;

  uint32_t count = 0;

  while (
    micros() - start <
    duration
  ) {

    int16_t ax;
    int16_t ay;
    int16_t az;

    int16_t gx;
    int16_t gy;
    int16_t gz;

    if (
      readMPU(
        ax,
        ay,
        az,
        gx,
        gy,
        gz
      )
    ) {

      sumX += gx;
      sumY += gy;
      sumZ += gz;

      count++;
    }

    delay(2);
  }

  if (count < 100) {

    Serial.println(
      "GYRO CALIBRATION FAILED"
    );

    return false;
  }

  gyroBiasX =
    (float)sumX /
    (float)count;

  gyroBiasY =
    (float)sumY /
    (float)count;

  gyroBiasZ =
    (float)sumZ /
    (float)count;

  Serial.print(
    "Bias X = "
  );

  Serial.println(
    gyroBiasX,
    3
  );

  Serial.print(
    "Bias Y = "
  );

  Serial.println(
    gyroBiasY,
    3
  );

  Serial.print(
    "Bias Z = "
  );

  Serial.println(
    gyroBiasZ,
    3
  );

  Serial.println(
    "GYRO CALIBRATION COMPLETE"
  );

  return true;
}


// =====================================================
// SEND UDP
// =====================================================

void sendUDP(
  uint32_t timestamp,
  uint32_t sequence,

  float leftRev,
  float rightRev,

  int16_t ax,
  int16_t ay,
  int16_t az,

  float gx,
  float gy,
  float gz,

  bool leftOK,
  bool rightOK,
  bool imuOK
) {

  udp.beginPacket(
    laptopIP,
    UDP_PORT
  );

  udp.print("{");

  udp.print(
    "\"device\":\"odom\""
  );

  udp.print(
    ",\"seq\":"
  );

  udp.print(sequence);

  udp.print(
    ",\"t\":"
  );

  udp.print(timestamp);

  udp.print(
    ",\"left\":"
  );

  udp.print(
    leftRev,
    6
  );

  udp.print(
    ",\"right\":"
  );

  udp.print(
    rightRev,
    6
  );

  // ---------------------------------------------------
  // Accelerometer
  // ---------------------------------------------------

  udp.print(
    ",\"ax\":"
  );

  udp.print(
    ax
  );

  udp.print(
    ",\"ay\":"
  );

  udp.print(
    ay
  );

  udp.print(
    ",\"az\":"
  );

  udp.print(
    az
  );

  // ---------------------------------------------------
  // FILTERED + BIAS-CORRECTED GYRO
  // ---------------------------------------------------
  //
  // Units remain raw MPU6500 counts.
  //
  // Divide by 131.0 on laptop to obtain deg/s.
  // ---------------------------------------------------

  udp.print(
    ",\"gx\":"
  );

  udp.print(
    gx,
    3
  );

  udp.print(
    ",\"gy\":"
  );

  udp.print(
    gy,
    3
  );

  udp.print(
    ",\"gz\":"
  );

  udp.print(
    gz,
    3
  );

  // ---------------------------------------------------
  // Status
  // ---------------------------------------------------

  udp.print(
    ",\"leftOK\":"
  );

  udp.print(
    leftOK ? "true" : "false"
  );

  udp.print(
    ",\"rightOK\":"
  );

  udp.print(
    rightOK ? "true" : "false"
  );

  udp.print(
    ",\"imuOK\":"
  );

  udp.print(
    imuOK ? "true" : "false"
  );

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

  udp.print(
    "\"device\":\"odom_status\""
  );

  udp.print(
    ",\"ready\":true"
  );

  udp.print(
    ",\"started\":"
  );

  udp.print(
    mappingStarted
      ? "true"
      : "false"
  );

  udp.print(
    ",\"seq\":"
  );

  udp.print(
    sequenceNumber
  );

  udp.print("}");

  udp.endPacket();
}


// =====================================================
// HANDLE CONTROL
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
  // START
  // ---------------------------------------------------

  if (
    strcmp(command, "START") == 0
  ) {

    mappingStartMicros =
      micros();

    sequenceNumber = 0;

    packetCount = 0;

    mappingStarted = true;

    Serial.println();
    Serial.println(
      ">>> MAPPING STARTED <<<"
    );

    sendStatus();
  }

  // ---------------------------------------------------
  // RESET
  // ---------------------------------------------------

  else if (
    strcmp(command, "RESET") == 0
  ) {

    mappingStarted = false;

    mappingStartMicros = 0;

    sequenceNumber = 0;

    Serial.println();
    Serial.println(
      ">>> MAPPING RESET <<<"
    );

    sendStatus();
  }
}


// =====================================================
// STATISTICS
// =====================================================

void printStatistics() {

  uint32_t now =
    millis();

  if (
    now - lastStatsMillis <
    1000
  ) {
    return;
  }

  uint32_t currentCount =
    packetCount;

  uint32_t rate =
    currentCount -
    lastStatsPacketCount;

  Serial.print(
    "ODOM: "
  );

  Serial.print(
    rate
  );

  Serial.print(
    " Hz | total="
  );

  Serial.print(
    currentCount
  );

  Serial.print(
    " | Lerr="
  );

  Serial.print(
    leftEncoderErrors
  );

  Serial.print(
    " | Rerr="
  );

  Serial.print(
    rightEncoderErrors
  );

  Serial.print(
    " | IMUerr="
  );

  Serial.print(
    imuErrors
  );

  Serial.print(
    " | mapping="
  );

  Serial.println(
    mappingStarted
      ? "ON"
      : "OFF"
  );

  lastStatsPacketCount =
    currentCount;

  lastStatsMillis =
    now;
}


// =====================================================
// WIFI
// =====================================================

bool connectWiFi() {

  Serial.println();
  Serial.println(
    "Connecting to WiFi..."
  );

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

  if (
    WiFi.status() != WL_CONNECTED
  ) {

    Serial.println(
      "WIFI CONNECTION FAILED!"
    );

    return false;
  }

  Serial.println(
    "WIFI CONNECTED!"
  );

  Serial.print(
    "ESP32 IP: "
  );

  Serial.println(
    WiFi.localIP()
  );

  Serial.print(
    "RSSI: "
  );

  Serial.print(
    WiFi.RSSI()
  );

  Serial.println(
    " dBm"
  );

  udp.begin(
    UDP_PORT
  );

  controlUdp.begin(
    CONTROL_PORT
  );

  return true;
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(
    115200
  );

  delay(1000);

  Serial.println();
  Serial.println(
    "===================================="
  );

  Serial.println(
    "      FINAL ODOMETRY ESP32"
  );

  Serial.println(
    "===================================="
  );

  // ---------------------------------------------------
  // I2C BUS 1
  // ---------------------------------------------------

  I2C_1.begin(
    SDA1,
    SCL1,
    400000
  );

  // ---------------------------------------------------
  // I2C BUS 2
  // ---------------------------------------------------

  I2C_2.begin(
    SDA2,
    SCL2,
    400000
  );

  delay(300);

  // ---------------------------------------------------
  // MPU6500
  // ---------------------------------------------------

  imuOK =
    initMPU6500();

  if (!imuOK) {

    Serial.println(
      "WARNING: MPU6500 unavailable."
    );
  }

  // ---------------------------------------------------
  // GYRO CALIBRATION
  // ---------------------------------------------------

  if (imuOK) {

    if (!calibrateGyro()) {
      imuOK = false;
    }
  }

  // ---------------------------------------------------
  // WiFi
  // ---------------------------------------------------

  connectWiFi();

  // ---------------------------------------------------
  // Start LiDAR rotation motor
  // ---------------------------------------------------

  setupMotor();

  // ---------------------------------------------------
  // Initial encoder state
  // ---------------------------------------------------

  bool leftOK;
  bool rightOK;

  uint16_t leftRaw =
    readAS5600(
      I2C_1,
      leftOK
    );

  uint16_t rightRaw =
    readAS5600(
      I2C_2,
      rightOK
    );

  if (leftOK) {

    updateEncoder(
      leftEncoder,
      leftRaw
    );
  }

  if (rightOK) {

    updateEncoder(
      rightEncoder,
      rightRaw
    );
  }

  // ---------------------------------------------------
  // Mapping state
  // ---------------------------------------------------

  mappingStarted = false;

  sequenceNumber = 0;

  lastStatsMillis =
    millis();

  Serial.println();
  Serial.println(
    "===================================="
  );

  Serial.println(
    "ODOMETRY READY"
  );

  Serial.println(
    "Output rate: 100 Hz"
  );

  Serial.println(
    "Waiting for START command..."
  );

  Serial.println(
    "===================================="
  );
}


// =====================================================
// LOOP
// =====================================================

void loop() {

  static uint32_t nextSampleTime =
    micros();

  static uint32_t previousSampleTime =
    micros();

  // ---------------------------------------------------
  // Control commands
  // ---------------------------------------------------

  handleControl();

  // ---------------------------------------------------
  // Wait for next deterministic sample
  // ---------------------------------------------------

  uint32_t now =
    micros();

  if (
    (int32_t)(
      now - nextSampleTime
    ) < 0
  ) {

    printStatistics();

    return;
  }

  nextSampleTime +=
    ODOM_PERIOD_US;

  // ---------------------------------------------------
  // Actual dt
  // ---------------------------------------------------

  uint32_t sampleNow =
    micros();

  float dt =
    (sampleNow -
     previousSampleTime) *
    1e-6f;

  previousSampleTime =
    sampleNow;

  // ---------------------------------------------------
  // Prevent insane dt after startup
  // ---------------------------------------------------

  if (
    dt <= 0.0f ||
    dt > 0.1f
  ) {

    dt =
      1.0f /
      ODOM_RATE_HZ;
  }

  // ---------------------------------------------------
  // LEFT ENCODER
  // ---------------------------------------------------

  bool leftOK;

  uint16_t leftRaw =
    readAS5600(
      I2C_1,
      leftOK
    );

  if (leftOK) {

    updateEncoder(
      leftEncoder,
      leftRaw
    );
  }

  else {

    leftEncoderErrors++;
  }

  // ---------------------------------------------------
  // RIGHT ENCODER
  // ---------------------------------------------------

  bool rightOK;

  uint16_t rightRaw =
    readAS5600(
      I2C_2,
      rightOK
    );

  if (rightOK) {

    updateEncoder(
      rightEncoder,
      rightRaw
    );
  }

  else {

    rightEncoderErrors++;
  }

  // ---------------------------------------------------
  // MPU6500
  // ---------------------------------------------------

  int16_t ax = 0;
  int16_t ay = 0;
  int16_t az = 0;

  int16_t rawGx = 0;
  int16_t rawGy = 0;
  int16_t rawGz = 0;

  bool currentImuOK =
    readMPU(
      ax,
      ay,
      az,
      rawGx,
      rawGy,
      rawGz
    );

  if (!currentImuOK) {

    imuErrors++;
  }

  // ---------------------------------------------------
  // FILTER IMU
  // ---------------------------------------------------

  if (currentImuOK) {

    filterGyro(
      rawGx,
      rawGy,
      rawGz,
      dt
    );

    filterAccel(
      ax,
      ay,
      az,
      dt
    );

    filterInitialized =
      true;
  }

  // ---------------------------------------------------
  // Only transmit mapping data after START
  // ---------------------------------------------------

  if (
    mappingStarted &&
    WiFi.status() == WL_CONNECTED
  ) {

    uint32_t timestamp =
      micros() -
      mappingStartMicros;

    sendUDP(
      timestamp,
      sequenceNumber,

      leftEncoder.revolutions,
      rightEncoder.revolutions,

      ax,
      ay,
      az,

      filteredGx,
      filteredGy,
      filteredGz,

      leftOK,
      rightOK,
      currentImuOK
    );

    sequenceNumber++;

    packetCount++;
  }

  // ---------------------------------------------------
  // Statistics
  // ---------------------------------------------------

  printStatistics();
}