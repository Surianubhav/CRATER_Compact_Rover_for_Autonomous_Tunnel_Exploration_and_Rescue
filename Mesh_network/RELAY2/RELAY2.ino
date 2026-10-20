#include <MineMesh.h>

#define MY_ID ID_RELAY2

MineMesh mesh;
uint32_t lastPrint = 0;

// Nothing is ever addressed to a relay - it only forwards other nodes' packets.
void onDeliver(const MmHeader& h, const uint8_t* b, uint8_t n) {}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("%s starting...\n", mmName(MY_ID));
  mesh.verbose = true;
  mesh.begin(MY_ID, onDeliver, 2);     // on-board LED (GPIO2) blinks on every forwarded packet
}

void loop() {
  mesh.update();
  if (millis() - lastPrint >= 3000) { lastPrint = millis(); mesh.printStatus(); }
}