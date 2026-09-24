"""Detection backends behind one protocol.

The ingestion engine never talks to a concrete implementation — it consumes
an iterable of FrameSample(ts, occupancy, items_handed). `RealYoloDetector`
genuinely runs YOLOv8 person detection + ByteTrack multi-object tracking
(and an optional supervision-style midline tripwire for handed items) when the
CV extras are installed and a source/model is available. `SimulatorDetector`
produces deterministic, scriptable sample streams so every demo runs without
footage, GPU or network — and the rest of the pipeline (baseline, anomaly,
alerts) is identical either way.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from app.config import settings

# Item classes plausibly counted at a distribution desk (COCO ids subset).
_TRIPWIRE_ITEM_CLASSES = {25: "backpack", 41: "cup", 39: "bottle", 44: "bowl", 63: "box"}


@dataclass
class FrameSample:
    ts: datetime
    occupancy: int       # distinct persons tracked in this frame/window
    items_handed: int    # tripwire crossings counted in this window
    raw: dict | None = None


class DetectorUnavailable(Exception):
    """Raised when a requested real detector cannot be initialised."""


class BaseDetector:
    backend_name = "base"

    def samples(self, source: str, seconds: int, every_n: int = 1) -> Iterator[FrameSample]:
        raise NotImplementedError


class SimulatorDetector(BaseDetector):
    """Deterministic, scripted activity stream.

    Seeded from the camera id so every run reproduces the same pattern; an
    explicit `profile` (used by the demo surge trigger) overrides the window
    contents so scenario A is scriptable end-to-end.
    """

    backend_name = "simulator"

    def __init__(self, seed: int | str = 0):
        self._rng = random.Random(f"omniwatch-sim-{seed}")

    def samples(self, source: str, seconds: int = 60, every_n: int = 1,
                profile: list[dict] | None = None) -> Iterator[FrameSample]:
        if profile:
            base_ts = datetime.now(timezone.utc) - timedelta(seconds=len(profile))
            for i, point in enumerate(profile):
                yield FrameSample(
                    ts=base_ts + timedelta(seconds=i),
                    occupancy=int(point.get("occupancy", 0)),
                    items_handed=int(point.get("items", 0)),
                )
            return
        # Normal drift: slow oscillation around a stable level (healthy centre).
        base = 8 + self._rng.uniform(-2, 2)
        amp = 2.5
        period = max(6, int(seconds / 5))
        n = max(1, seconds)
        start = datetime.now(timezone.utc)
        for i in range(n):
            wave = math.sin((2 * math.pi * i) / period)
            noise = self._rng.uniform(-1.2, 1.2)
            occupancy = max(0, int(round(base + amp * wave + noise)))
            items = max(0, int(round(occupancy * 0.8 * self._rng.uniform(0.7, 1.0))))
            yield FrameSample(ts=start + timedelta(seconds=i), occupancy=occupancy, items_handed=items)


class RealYoloDetector(BaseDetector):
    """YOLOv8 person/object detection + ByteTrack tracking over a stream/file.

    Imports the heavy stack lazily: constructing the detector fails with
    DetectorUnavailable if the CV extras or the model file are missing, which
    the engine treats as a signal to fall back to the simulator under CV_MODE=auto.
    """

    backend_name = "yolo-bytetrack"

    def __init__(self, model_path: str | None = None, every_n: int = 5):
        self._every_n = max(1, int(every_n or settings.cv_sample_every_frames))
        self._model_path = model_path or settings.yolo_model_path or "yolov8n.pt"
        try:
            from ultralytics import YOLO  # type: ignore
            from supervision import ByteTrack  # type: ignore
        except Exception as exc:  # noqa: BLE001 - dependency absence
            raise DetectorUnavailable(
                f"CV extras not installed ({exc}); install requirements-cv.txt"
            ) from exc
        try:
            self._model = YOLO(self._model_path)
        except Exception as exc:  # noqa: BLE001
            raise DetectorUnavailable(f"Could not load YOLO model {self._model_path}: {exc}") from exc
        self._tracker = ByteTrack()
        self._supervision = __import__("supervision")

    def samples(self, source: str, seconds: int = 60, every_n: int = 1) -> Iterator[FrameSample]:
        if not source:
            raise DetectorUnavailable("No video source configured")
        try:
            import cv2  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise DetectorUnavailable("opencv not installed") from exc

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise DetectorUnavailable(f"Cannot open video source: {source}")
        try:
            from supervision import Detections  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise DetectorUnavailable("supervision unavailable") from exc

        frame_idx = 0
        handled = 0
        start = datetime.now(timezone.utc)
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_idx += 1
                if frame_idx % self._every_n != 0:
                    continue
                results = self._model.predict(frame, verbose=False)
                item_boxes = []
                for r in results:
                    if r.boxes is None or r.boxes.cls is None:
                        continue
                    cls = r.boxes.cls.cpu().tolist()
                    xyxy = r.boxes.xyxy.cpu().tolist()
                    for c, box in zip(cls, xyxy):
                        if c in _TRIPWIRE_ITEM_CLASSES:
                            item_boxes.append({"box": box, "cls": int(c)})
                # Occupancy: ByteTrack over person-class detections only.
                detections = Detections.from_ultralytics(results[0])
                persons = detections[detections.class_id == 0]
                if len(persons) > 0:
                    tracked = self._tracker.update_with_detections(persons)
                    occupancy = int(len(set(tracked.tracker_id.tolist()))) if tracked.tracker_id is not None else 0
                else:
                    occupancy = 0
                # Simplified midline tripwire for handout items (mirrors supervision LineZone).
                for item in item_boxes:
                    y = (item["box"][1] + item["box"][3]) / 2
                    mid = frame.shape[0] / 2
                    if y > mid:  # item crossed the desk midline downward
                        handled += 1
                yield FrameSample(ts=start + timedelta(seconds=frame_idx / 30.0),
                                  occupancy=occupancy, items_handed=handled)
                handled = 0
                if frame_idx >= seconds * 30:
                    break
        finally:
            cap.release()


def resolve_detector(camera, *, force_sim: bool = False) -> BaseDetector:
    """Pick a detector for a camera honouring CV_MODE (auto | real | sim)."""
    mode = settings.cv_mode if not force_sim else "sim"
    if mode == "sim":
        return SimulatorDetector(seed=camera.id or 0)
    # Camera source type simulator always uses the simulator.
    if getattr(camera, "source_type", None) == "simulator" or mode == "auto":
        try:
            if getattr(camera, "source_type", None) not in ("rtsp", "rtmp", "mjpeg", "file") or not camera.url:
                raise DetectorUnavailable("no real stream source")
            return RealYoloDetector()
        except DetectorUnavailable:
            return SimulatorDetector(seed=camera.id or 0)
    return RealYoloDetector()
