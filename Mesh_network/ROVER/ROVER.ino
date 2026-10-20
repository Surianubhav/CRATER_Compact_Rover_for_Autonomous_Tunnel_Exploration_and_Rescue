#include <MineMesh.h>

#define MY_ID        ID_ROVER
#define TELEMETRY_MS 1000

MineMesh mesh;

// =================== SENSOR LAYER (simulated today) ===================
// Later: replace the body of readSensors() with real MQ-4 / MQ-7 / BME680 /
// MPU6050 / battery readings. Nothing else in this file or the mesh changes.
struct SensorData { float tempC, humidity, rollDeg, pitchDeg, battV; uint16_t ch4, co; };
bool stopped = false;

void readSensors(SensorData &s) {
  float t = millis() / 1000.0f;
  float moving = stopped ? 0.0f : 1.0f;
  s.tempC    = 28.0f + 1.8f * sin(t / 23.0f) + 0.3f * sin(t * 1.7f);
  s.humidity = 64.0f + 4.0f * sin(t / 31.0f) + 0.5f * sin(t * 0.9f);
  s.ch4      = (uint16_t)(180 + 25 * sin(t / 17.0f) + random(-4, 5));
  s.co       = (uint16_t)(60 + 9 * sin(t / 29.0f) + random(-2, 3));
  s.rollDeg  = moving * (3.0f * sin(t / 2.7f));
  s.pitchDeg = moving * (1.5f * sin(t / 3.9f + 1.0f));
  s.battV    = 12.4f - 0.0008f * t;
  if (s.battV < 10.5f) s.battV = 10.5f;
}

// =================== TELEMETRY PACKER ===================
void packTelemetry(const SensorData &s, MmTelemetry &t) {
  t.temp10  = (int16_t)(s.tempC * 10.0f);
  t.hum10   = (int16_t)(s.humidity * 10.0f);
  t.ch4     = s.ch4;
  t.co      = s.co;
  t.roll10  = (int16_t)(s.rollDeg * 10.0f);
  t.pitch10 = (int16_t)(s.pitchDeg * 10.0f);
  t.batt100 = (uint16_t)(s.battV * 100.0f);
}

// =================== APPLICATION STATE ===================
uint16_t pktCount = 0;
uint16_t lastRtt = 0;
uint32_t lastTel = 0;
bool     noRoute = false;
uint16_t retryNo = 0;
uint16_t sentSeq[16];
uint32_t sentAt[16];

void sendTelemetry() {
  SensorData s; readSensors(s);
  MmTelemetry t; memset(&t, 0, sizeof(t));
  packTelemetry(s, t);
  t.rttMs = lastRtt;
  t.pktCount = pktCount + 1;
  t.flags = stopped ? 1 : 0;

  uint16_t seq = 0;
  if (mesh.send(ID_BASE, MM_TELEMETRY, &t, sizeof(t), &seq)) {
    pktCount++;
    sentSeq[seq & 15] = seq; sentAt[seq & 15] = millis();
    if (noRoute) { noRoute = false; Serial.println("ROUTE FOUND - communication resumed"); }
    retryNo = 0;
    Serial.printf("TX #%u -> BASE via %s (cost %u)  temp=%.1f ch4=%u co=%u batt=%.2f\n",
                  pktCount, mmName(mesh.routes[ID_BASE].next), (unsigned)mesh.routes[ID_BASE].metric,
                  s.tempC, s.ch4, s.co, s.battV);
  } else {
    if (!noRoute) { noRoute = true; retryNo = 0; Serial.println("NO ROUTE to BASE - RETRYING..."); }
    retryNo++;
    Serial.printf("NO ROUTE - RETRY #%u\n", retryNo);
  }
}

// =================== PACKETS ADDRESSED TO THE ROVER ===================
void onDeliver(const MmHeader& h, const uint8_t* b, uint8_t n) {
  if (h.type == MM_ACK && n >= sizeof(MmAck)) {
    MmAck a; memcpy(&a, b, sizeof(a));
    if (sentSeq[a.ackSeq & 15] == a.ackSeq) {
      uint32_t rtt = millis() - sentAt[a.ackSeq & 15];
      lastRtt = rtt > 65535 ? 65535 : (uint16_t)rtt;
    }
  }
  else if (h.type == MM_COMMAND && n >= sizeof(MmCommand)) {
    MmCommand c; memcpy(&c, b, sizeof(c));
    const char* nm = "?";
    if      (c.cmd == CMD_PING)   nm = "PING";
    else if (c.cmd == CMD_STATUS) nm = "STATUS";
    else if (c.cmd == CMD_STOP)   { nm = "STOP"; stopped = true; }
    else if (c.cmd == CMD_GO)     { nm = "GO";   stopped = false; }
    Serial.printf("COMMAND %s received (id %u) - replying\n", nm, c.cmdId);

    MmResponse r; memset(&r, 0, sizeof(r));
    r.cmd = c.cmd; r.cmdId = c.cmdId; r.result = 0;
    r.flags = stopped ? 1 : 0;
    r.uptimeS = millis() / 1000;
    r.pktCount = pktCount;
    mesh.send(h.src, MM_RESPONSE, &r, sizeof(r));
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("ROVER starting...");
  mesh.verbose = true;
  mesh.begin(MY_ID, onDeliver, 2);     // GPIO2 = on-board LED: blinks on every packet sent
}

void loop() {
  mesh.update();
  uint32_t now = millis();
  if (now - lastTel >= TELEMETRY_MS) { lastTel = now; sendTelemetry(); }
}