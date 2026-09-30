"""
Thermal inference adapter.

Wraps the EXISTING trained model at backend/models/yolov8_thermal_best.pt
(single class: "person" -- see /training/dataset.yaml). This module does
not retrain, fine-tune or otherwise modify that model. It only:

  1. loads it once, off the request path, with a clear LOADING/READY/ERROR
     state instead of crashing the process if the file or ultralytics/torch
     is missing (this backend previously did `raise FileNotFoundError` at
     *import time* against a hardcoded Windows path -- that bug is fixed
     here: the path now defaults to the model file that already ships in
     this repo, and a missing/broken model degrades to an explicit
     MODEL_ERROR state instead of taking the whole API down);
  2. runs inference and extracts what the model already gives us
     (label, confidence, box coordinates);
  3. derives a few additional display fields the console needs
     (percentage bbox, a cropped thumbnail, a simple stable track id)
     from that same output -- it does not invent detections.

IMPORTANT HONESTY NOTE: this model is a visual object detector (trained
on thermal-style imagery), not a radiometric thermal camera -- it does
not measure real per-pixel temperature. `max_temperature_c` and
`temperature_delta_c` below are ESTIMATED from relative pixel intensity
in a white-hot palette image (brighter -> hotter) and are clearly marked
`estimated_thermal=True` in the schema and in the UI. They should be
replaced with real radiometric readings once a calibrated thermal sensor
is available.
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np

from app.config.settings import get_settings
from app.models.schemas import BBox, DataSource, ThermalConnectionState, ThermalDetection

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# ---------------------------------------------------------------------------
# Simple IoU-based tracker so a person walking across a few frames keeps the
# same H-01 style id instead of spawning a new detection every frame.
# ---------------------------------------------------------------------------
@dataclass
class _Track:
    track_id: str
    bbox_pct: tuple
    last_seen: float


class _SimpleTracker:
    def __init__(self, max_age_s: float = 6.0, iou_threshold: float = 0.25):
        self._tracks: dict[str, _Track] = {}
        self._next_num = 1
        self._max_age_s = max_age_s
        self._iou_threshold = iou_threshold
        self._lock = Lock()

    @staticmethod
    def _iou(a: tuple, b: tuple) -> float:
        ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
        bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax1, bx1), min(ay1, by1)
        iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
        inter = iw * ih
        union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
        return inter / union if union > 0 else 0.0

    def assign(self, bbox_pct: tuple, now: float) -> str:
        with self._lock:
            # drop stale tracks
            self._tracks = {
                k: v for k, v in self._tracks.items() if now - v.last_seen <= self._max_age_s
            }
            best_id, best_iou = None, 0.0
            for tid, tr in self._tracks.items():
                iou = self._iou(tr.bbox_pct, bbox_pct)
                if iou > best_iou:
                    best_iou, best_id = iou, tid
            if best_id is not None and best_iou >= self._iou_threshold:
                self._tracks[best_id] = _Track(best_id, bbox_pct, now)
                return best_id
            new_id = f"H-{self._next_num:02d}"
            self._next_num += 1
            self._tracks[new_id] = _Track(new_id, bbox_pct, now)
            return new_id


class ThermalAdapter:
    """Process-wide singleton around the trained detection model."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None
        self._model_names: dict[int, str] = {}
        self._state = ThermalConnectionState.DISCONNECTED
        self._error_message: Optional[str] = None
        self._lock = Lock()
        self._tracker = _SimpleTracker()

    # -- lifecycle -----------------------------------------------------
    @property
    def state(self) -> ThermalConnectionState:
        return self._state

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message

    @property
    def model_name(self) -> str:
        return self._settings.MODEL_PATH.name

    def load(self) -> None:
        """Load the model once. Safe to call multiple times."""
        with self._lock:
            if self._model is not None or self._state == ThermalConnectionState.MODEL_ERROR:
                return
            self._state = ThermalConnectionState.CONNECTING
            if not self._settings.THERMAL_ENABLED:
                self._state = ThermalConnectionState.DISCONNECTED
                self._error_message = "Thermal inference disabled (MINESWEEPER_THERMAL_ENABLED=0)."
                return
            model_path: Path = self._settings.MODEL_PATH
            if not model_path.exists():
                self._state = ThermalConnectionState.MODEL_ERROR
                self._error_message = f"Model file not found at {model_path}"
                return
            try:
                from ultralytics import YOLO  # imported lazily so the rest of the
                                                # backend still runs without torch installed
            except ImportError as exc:
                self._state = ThermalConnectionState.MODEL_ERROR
                self._error_message = (
                    "ultralytics/torch not installed in this environment. "
                    f"Install backend/requirements.txt to enable live inference. ({exc})"
                )
                return
            try:
                self._model = YOLO(str(model_path))
                self._model_names = self._model.names
                self._state = ThermalConnectionState.LIVE
                self._error_message = None
            except Exception as exc:  # noqa: BLE001 - surface any load failure as MODEL_ERROR
                self._state = ThermalConnectionState.MODEL_ERROR
                self._error_message = f"Failed to load model: {exc}"

    # -- inference -------------------------------------------------------
    def run_inference(self, frame_bgr: np.ndarray, source: DataSource = DataSource.LIVE):
        """
        Run the existing model on a single BGR frame (numpy array, as
        decoded by cv2.imdecode). Returns (detections, scene_avg_c,
        scene_max_c, annotated_frame_bgr, inference_ms) or raises if the
        model is not currently usable -- caller is expected to have
        checked `.state == LIVE` first.
        """
        if self._model is None or cv2 is None:
            raise RuntimeError("Thermal model is not loaded")

        t0 = time.time()
        results = self._model(frame_bgr, conf=self._settings.MODEL_CONF_THRESHOLD, verbose=False)
        result = results[0]
        annotated = result.plot()  # model's own visualization (unmodified behaviour)
        inference_ms = (time.time() - t0) * 1000.0

        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        scene_avg_intensity = float(gray.mean())

        detections: list[ThermalDetection] = []
        now = time.time()

        for box in result.boxes:
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            label = self._model_names.get(cls, "object")
            xyxy = box.xyxy[0].tolist()
            x0, y0, x1, y1 = xyxy
            bbox_pct = (
                round((x0 / w) * 100, 2),
                round((y0 / h) * 100, 2),
                round(((x1 - x0) / w) * 100, 2),
                round(((y1 - y0) / h) * 100, 2),
            )
            track_id = self._tracker.assign(bbox_pct, now)

            # -- estimated "thermal" stats derived from pixel intensity in
            # the box, for a plausible-but-explicitly-estimated readout.
            region = gray[max(0, int(y0)):int(y1), max(0, int(x0)):int(x1)]
            region_intensity = float(region.mean()) if region.size else scene_avg_intensity
            # Map 0-255 intensity delta onto a illustrative +0..+15C band above
            # a nominal 22C ambient baseline -- see module docstring.
            delta_c = round(max(0.0, (region_intensity - scene_avg_intensity) / 255.0 * 15.0) + 6.0, 1)
            max_temp_c = round(22.0 + delta_c, 1)

            tags = []
            if label == "person":
                tags.append("HUMAN SIGNATURE")
            if max_temp_c >= 45:
                tags.append("HOT SPOT")
            if max_temp_c >= 60:
                tags.append("POSSIBLE FIRE")

            thumb_uri = None
            if region.size:
                ok, buf = cv2.imencode(".jpg", frame_bgr[max(0, int(y0)):int(y1), max(0, int(x0)):int(x1)])
                if ok:
                    thumb_uri = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

            detections.append(
                ThermalDetection(
                    id=track_id,
                    type=label,
                    confidence=round(conf, 4),
                    timestamp=now,
                    bbox=BBox(
                        x_pct=bbox_pct[0], y_pct=bbox_pct[1],
                        width_pct=bbox_pct[2], height_pct=bbox_pct[3],
                    ),
                    temperature_delta_c=delta_c,
                    max_temperature_c=max_temp_c,
                    estimated_thermal=True,
                    classification_tags=tags,
                    thumbnail_data_uri=thumb_uri,
                )
            )

        scene_avg_c = round(22.0 + max(0.0, (scene_avg_intensity - 90.0) / 255.0 * 10.0), 1)
        scene_max_c = max([d.max_temperature_c for d in detections], default=scene_avg_c)

        return detections, scene_avg_c, scene_max_c, annotated, inference_ms


_adapter_singleton: Optional[ThermalAdapter] = None


def get_thermal_adapter() -> ThermalAdapter:
    global _adapter_singleton
    if _adapter_singleton is None:
        _adapter_singleton = ThermalAdapter()
    return _adapter_singleton
