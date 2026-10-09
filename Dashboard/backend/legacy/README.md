# Legacy prototype backend

`app.py` in this folder is the original single-file FastAPI prototype
that shipped with this repo before the MINESWEEPER console rebuild. It
is kept here for reference only and is **not** wired into the running
application anymore.

It had one real bug worth noting: the model path was hardcoded to a
Windows path (`C:\Users\click\Downloads\...`), so it would crash on load
on any other machine. The new backend (`backend/app/`) fixes this by
resolving the model path relative to the repo
(`backend/models/yolov8_thermal_best.pt`), configurable via the
`MINESWEEPER_MODEL_PATH` environment variable -- see
`backend/app/adapters/thermal_adapter.py`.

The detection logic itself (load YOLO model, run inference, return
label + confidence) was reused, not rewritten -- it's now wrapped by
`backend/app/adapters/thermal_adapter.py` instead of living directly in
a route handler.
