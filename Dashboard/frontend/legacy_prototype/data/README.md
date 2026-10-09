# MINEGUARD data files

These JSON files are the dashboard's data layer. `pipeline.js` loads them
and hands the parsed data to the render functions in `script.js`. Nothing
in `script.js` needs to change when these files are replaced by real
data — that's the point of splitting them out.

## sensor-data.json
Current format matches the hardware team's exact JSON output
(`mq4`, `mq7`, `temp`, `hum`, `pressure`, `alt`, `bmp_ok`).

**Future:** replace the `fetch("data/sensor-data.json")` call in
`pipeline.js` with a call to the real sensor endpoint or a WebSocket
subscription (e.g. `GET /api/sensors` or a push message), keeping the
same field names, then call `updateSensorData(newData)` whenever fresh
readings arrive.

## mesh-data.json
Mock ESP mesh state: deployed nodes, their status/role, and the current
route the sensor data is taking back to the rover.

**Future:** replace with `GET /api/mesh` or a push update from the mesh
coordinator. Shape should stay `{ route: [...], hops: N, activeNodes: N,
nodes: { "ESP-01": { status, role, packetsForwarded, lastPacketSec,
onRoute }, ... } }`.

## thresholds.json
Gas warning/critical thresholds used to color-code the MQ-4 / MQ-7
readings. Explicitly **not** scientifically calibrated — placeholder
values only.

**Future:** replace with calibrated limits from the sensing team, or
make this endpoint admin-configurable so thresholds can be tuned without
touching code.

## thermal-samples.json
Example outputs shaped exactly like what the real thermal human-detection
model is expected to return:
```
{ "detected": true, "confidence": 0.91, "bbox": [x1,y1,x2,y2], "person_id": 1 }
```
`bbox` coordinates are percentages of the image (0–100), so the overlay
scales with whatever image size is shown. The frontend currently picks
one of these at random when "Run Detection" is clicked, to simulate a
model response arriving.

**Future:** replace `runThermalDetection()` in `script.js` with a real
call, e.g. `POST /api/thermal-detection` with the uploaded image, and
feed the single JSON object it returns straight into
`updateThermalResult(result)` — no other UI changes needed.

Later, motionless-tracking data is expected in a similar shape:
```
{ "motionless": true, "motionless_seconds": 134, "warning": true }
```
which maps directly onto `triggerMotionlessAlert()`.

## events-seed.json
Initial entries shown in the event log on page load, so the dashboard
doesn't open empty.

**Future:** once hardware/backend is connected, drop this file and push
real events into `addEvent(message, type)` as they happen instead.
