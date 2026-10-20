#include <MineMesh.h>

#define MY_ID ID_BASE

MineMesh mesh;

struct Pending { bool active; uint8_t cmd; uint16_t cmdId; uint32_t sentAt; uint8_t attempts; };
Pending pend = {false, 0, 0, 0, 0};
uint16_t cmdCounter = 1;
uint32_t lastStatus = 0;
uint16_t noRouteSecs = 0;
String   rxLine;

const char* cmdName(uint8_t c) {
  switch (c) { case CMD_PING: return "PING"; case CMD_STATUS: return "STATUS";
               case CMD_STOP: return "STOP"; case CMD_GO: return "GO"; default: return "?"; }
}

void printPath(const MmHeader& h) {
  for (int i = 0; i < h.pathLen; i++) { if (i) Serial.print('-'); Serial.print(h.path[i]); }
}

// ---------- packets that arrive at BASE ----------
void onDeliver(const MmHeader& h, const uint8_t* b, uint8_t n) {
  if (h.type == MM_TELEMETRY && n >= sizeof(MmTelemetry)) {
    MmTelemetry t; memcpy(&t, b, sizeof(t));
    Serial.printf("TEL,%u,", t.pktCount);
    printPath(h);                                   // the REAL path, read from the packet
    Serial.printf(",%.1f,%.1f,%u,%u,%.1f,%.1f,%.2f,%u,%u\n",
                  t.temp10 / 10.0f, t.hum10 / 10.0f, t.ch4, t.co,
                  t.roll10 / 10.0f, t.pitch10 / 10.0f, t.batt100 / 100.0f, t.rttMs, t.flags);
    MmAck a; a.ackSeq = h.seq;                      // end-to-end ACK lets the rover measure RTT
    mesh.send(h.src, MM_ACK, &a, sizeof(a));
  }
  else if (h.type == MM_RESPONSE && n >= sizeof(MmResponse)) {
    MmResponse r; memcpy(&r, b, sizeof(r));
    bool mine = pend.active && pend.cmdId == r.cmdId;
    unsigned long rtt = mine ? (millis() - pend.sentAt) : 0;
    Serial.printf("RSP,%s,%u,", cmdName(r.cmd), r.cmdId);
    printPath(h);
    Serial.printf(",%lu,%s,", rtt, r.result == 0 ? "OK" : "FAIL");
    if (r.cmd == CMD_PING) Serial.println("PONG");
    else Serial.printf("uptime=%lus pkts=%u state=%s\n", (unsigned long)r.uptimeS, r.pktCount,
                       (r.flags & 1) ? "STOPPED" : "RUNNING");
    if (mine) pend.active = false;
  }
}

// ---------- commands from the dashboard ----------
bool trySendPending() {
  MmCommand c; c.cmd = pend.cmd; c.cmdId = pend.cmdId;
  bool ok = mesh.send(ID_ROVER, MM_COMMAND, &c, sizeof(c));
  pend.attempts++;
  pend.sentAt = millis();
  if (!ok) Serial.printf("EVT,%s attempt %u: NO ROUTE to ROVER\n", cmdName(pend.cmd), pend.attempts);
  return ok;
}

void issueCommand(uint8_t cmd) {
  pend.active = true; pend.cmd = cmd; pend.cmdId = cmdCounter++; pend.attempts = 0;
  trySendPending();
}

void handleCmdLine(String s) {
  s.trim(); s.toUpperCase();
  if (s.startsWith("CMD,")) s = s.substring(4);
  if      (s == "PING")   issueCommand(CMD_PING);
  else if (s == "STATUS") issueCommand(CMD_STATUS);
  else if (s == "STOP")   issueCommand(CMD_STOP);
  else if (s == "GO")     issueCommand(CMD_GO);
  else Serial.println("EVT,Unknown command (use PING, STATUS, STOP, GO)");
}

void pollSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (rxLine.length()) handleCmdLine(rxLine); rxLine = ""; }
    else if (rxLine.length() < 40) rxLine += c;
  }
}

// ---------- status line for the dashboard (from BASE's own routing table) ----------
void printStatusLine() {
  if (mesh.hasRoute(ID_ROVER)) noRouteSecs = 0; else noRouteSecs++;
  Serial.printf("ST,%lu", (unsigned long)(millis() / 1000));
  for (uint8_t d = 2; d <= 4; d++) Serial.printf(",%u,%u", (unsigned)mesh.routes[d].metric, (unsigned)mesh.routes[d].next);
  Serial.printf(",%u,%d\n", (unsigned)noRouteSecs, MM_LINK_FILTER);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("EVT,BASE starting");
  mesh.begin(MY_ID, onDeliver);
}

void loop() {
  mesh.update();
  pollSerial();
  uint32_t now = millis();

  if (now - lastStatus >= 1000) { lastStatus = now; printStatusLine(); }

  if (pend.active && now - pend.sentAt >= 1500) {          // retry commands up to 3 times
    if (pend.attempts < 3) { Serial.printf("EVT,%s retry #%u\n", cmdName(pend.cmd), pend.attempts); trySendPending(); }
    else { Serial.printf("RSP,%s,%u,-,0,TIMEOUT,no response from ROVER\n", cmdName(pend.cmd), pend.cmdId); pend.active = false; }
  }
}