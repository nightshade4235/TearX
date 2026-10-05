#!/usr/bin/env python3
"""GALILEO vision module: black-disk detection and distance parsing only.

System architecture:
    Raspberry Pi 4 = master: camera/input processing, decisions, and Servo HAT.
    ESP32 = motor-control slave: receives movement commands from the Pi.

This module does not control motors, servos, GPIO, or navigation. It returns
vision JSON to the Raspberry Pi decision layer. Run headless for systemd;
add --preview for a human display.

The detector cannot identify a disk from the word "black" alone. The most
important field calibration values are the camera ROI and the expected disk
pixel diameter at the actual operating distance.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Optional

import cv2
import numpy as np

# ----------------------------- known object -------------------------------
DISK_DIAMETER_MM = 56.0
FOCAL_LENGTH_PX = 520.0                 # Calibrate with the real Pi camera.
# Half of the camera's horizontal field of view. If the target is at the
# right edge, the requested turn angle is approximately +MAX_FOV_DEG; at the
# left edge it is approximately -MAX_FOV_DEG.
MAX_FOV_DEG = 32.0                      # MUST be calibrated for this camera.
CENTRE_DEADBAND_RATIO = 0.05            # +/-5% of image width is "centre".

# ----------------------------- camera -------------------------------------
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CAMERA_INDEX = 0

# Restrict detection to the part of the image where disks can appear.
# Set all four to None to use the full frame temporarily.
ROI_X1 = None
ROI_Y1 = None
ROI_X2 = None
ROI_Y2 = None

# If known, fill the apparent disk diameter range in pixels. This is the
# strongest protection against black wheels, holes, and distant shadows.
MIN_DISK_DIAMETER_PX = None
MAX_DISK_DIAMETER_PX = None

MAX_DISKS = 3
# Candidates below this score are not considered disks. Lower this only if
# real tilted disks are being rejected; raise it if lines/blobs get through.
MIN_DISKINESS = 0.62

# ------------------------- lighting / segmentation ------------------------
# Black disks under brighter light may have V > 60; 100 is a safer start.
HSV_S_MAX = 110
HSV_V_MAX = 105
USE_ADAPTIVE_DARK_MASK = True
ADAPTIVE_BLOCK_SIZE = 31               # Must be odd and >= 3.
ADAPTIVE_C = 7

# ------------------------- shape rejection --------------------------------
MIN_AREA_PX = 180
MAX_AREA_PX = 80_000
MIN_CIRCULARITY = 0.58                  # Higher rejects arbitrary blobs.
MAX_AXIS_RATIO = 3.0                   # Disk may be tilted, but not a line.
MIN_MINOR_AXIS_PX = 8.0
MIN_SOLIDITY = 0.88                     # Area / convex-hull area.
MIN_EXTENT = 0.45                       # Area / bounding-rectangle area.
MIN_ELLIPSE_FILL = 0.55
MAX_ELLIPSE_FILL = 1.20
REJECT_FRAME_BORDER = True
MORPH_KERNEL_SIZE = 3
MORPH_OPEN_ITERATIONS = 1
MORPH_CLOSE_ITERATIONS = 1


@dataclass(frozen=True)
class DiskDetection:
    cx_px: float
    cy_px: float
    width_px: float
    height_px: float
    major_axis_px: float
    minor_axis_px: float
    angle_deg: float
    angular_size_rad: float
    distance_mm: float
    confidence: float
    diskiness: float
    screen_position: str
    turn_angle_deg: float

    def as_dict(self) -> dict:
        return asdict(self)


def angular_size_from_pixels(pixel_size: float, focal_length_px: float) -> float:
    if pixel_size <= 0 or focal_length_px <= 0:
        raise ValueError("pixel_size and focal_length_px must be positive")
    return 2.0 * math.atan(pixel_size / (2.0 * focal_length_px))


def distance_from_angular_size(real_size_mm: float, angle_rad: float) -> float:
    denominator = 2.0 * math.tan(angle_rad / 2.0)
    return float("inf") if denominator <= 1e-12 else real_size_mm / denominator


def parse_distance(pixel_diameter: float) -> float:
    angle = angular_size_from_pixels(pixel_diameter, FOCAL_LENGTH_PX)
    return distance_from_angular_size(DISK_DIAMETER_MM, angle)


def screen_direction_and_turn_angle(
    centre_x_px: float, frame_width_px: int
) -> tuple[str, float]:
    """Return position and signed angle for the ESP32 movement command.

    Left of image centre is negative; right is positive. MAX_FOV_DEG is the
    calibrated half horizontal field of view, not the full field of view.
    """
    if frame_width_px <= 0:
        raise ValueError("frame_width_px must be positive")
    image_centre = frame_width_px / 2.0
    offset_ratio = (centre_x_px - image_centre) / image_centre
    if abs(offset_ratio) <= CENTRE_DEADBAND_RATIO:
        position = "centre"
    elif offset_ratio < 0:
        position = "left"
    else:
        position = "right"
    turn_angle = max(-MAX_FOV_DEG, min(MAX_FOV_DEG, offset_ratio * MAX_FOV_DEG))
    return position, float(turn_angle)


def _roi(frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    height, width = frame.shape[:2]
    x1 = 0 if ROI_X1 is None else max(0, min(width - 1, int(ROI_X1)))
    y1 = 0 if ROI_Y1 is None else max(0, min(height - 1, int(ROI_Y1)))
    x2 = width if ROI_X2 is None else max(x1 + 1, min(width, int(ROI_X2)))
    y2 = height if ROI_Y2 is None else max(y1 + 1, min(height, int(ROI_Y2)))
    return frame[y1:y2, x1:x2], (x1, y1)


def black_mask(frame_bgr: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    """Make a dark-object mask; adaptive mode helps with uneven lighting."""
    crop, offset = _roi(frame_bgr)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    fixed = cv2.inRange(
        hsv,
        np.array([0, 0, 0], dtype=np.uint8),
        np.array([179, HSV_S_MAX, HSV_V_MAX], dtype=np.uint8),
    )

    mask = fixed
    if USE_ADAPTIVE_DARK_MASK:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        block = max(3, int(ADAPTIVE_BLOCK_SIZE) | 1)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, block, ADAPTIVE_C,
        )
        # Require the pixel to be dark/low-saturation as well as locally dark.
        mask = cv2.bitwise_and(fixed, adaptive)

    k = max(3, int(MORPH_KERNEL_SIZE) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=MORPH_OPEN_ITERATIONS)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=MORPH_CLOSE_ITERATIONS)
    return mask, offset


def _candidate(
    contour: np.ndarray,
    offset: tuple[int, int],
    frame_width_px: int,
) -> Optional[DiskDetection]:
    area = cv2.contourArea(contour)
    if not (MIN_AREA_PX <= area <= MAX_AREA_PX) or len(contour) < 5:
        return None

    x, y, w, h = cv2.boundingRect(contour)
    if REJECT_FRAME_BORDER and (x <= 0 or y <= 0):
        return None

    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 1:
        return None
    circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    if circularity < MIN_CIRCULARITY:
        return None

    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = area / hull_area if hull_area > 0 else 0
    if solidity < MIN_SOLIDITY:
        return None

    extent = area / float(w * h) if w and h else 0
    if extent < MIN_EXTENT:
        return None

    (cx, cy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
    major = max(float(axis_a), float(axis_b))
    minor = min(float(axis_a), float(axis_b))
    if minor < MIN_MINOR_AXIS_PX or major / minor > MAX_AXIS_RATIO:
        return None
    if MIN_DISK_DIAMETER_PX is not None and major < MIN_DISK_DIAMETER_PX:
        return None
    if MAX_DISK_DIAMETER_PX is not None and major > MAX_DISK_DIAMETER_PX:
        return None

    ellipse_area = math.pi * (major / 2) * (minor / 2)
    fill = area / ellipse_area if ellipse_area > 0 else 0
    if not (MIN_ELLIPSE_FILL <= fill <= MAX_ELLIPSE_FILL):
        return None

    theta = angular_size_from_pixels(major, FOCAL_LENGTH_PX)
    distance = distance_from_angular_size(DISK_DIAMETER_MM, theta)
    full_cx = float(cx + offset[0])
    screen_position, turn_angle = screen_direction_and_turn_angle(
        full_cx, frame_width_px
    )
    # Confidence is diagnostic only; it is not an AI probability.
    axis_score = min(1.0, minor / major) if major > 0 else 0.0
    circularity_score = min(1.0, circularity / 0.785)
    solidity_score = min(1.0, solidity)
    extent_score = min(1.0, extent / 0.785)
    fill_score = min(1.0, fill)
    # Diskiness is a shape score, not an AI probability. A round, solid,
    # filled ellipse scores high; a thin line scores low through axis_score,
    # circularity_score, and extent_score.
    diskiness = (
        0.30 * circularity_score +
        0.25 * axis_score +
        0.20 * solidity_score +
        0.15 * extent_score +
        0.10 * fill_score
    )
    if diskiness < MIN_DISKINESS:
        return None
    confidence = diskiness

    return DiskDetection(
        cx_px=full_cx, cy_px=float(cy + offset[1]),
        width_px=float(w), height_px=float(h), major_axis_px=major,
        minor_axis_px=minor, angle_deg=float(angle),
        angular_size_rad=float(theta), distance_mm=float(distance),
        confidence=float(confidence),
        diskiness=float(diskiness),
        screen_position=screen_position,
        turn_angle_deg=turn_angle,
    )


def detect_disks(frame_bgr: np.ndarray) -> list[DiskDetection]:
    if frame_bgr is None or frame_bgr.ndim != 3:
        raise ValueError("Expected a BGR image")
    mask, offset = black_mask(frame_bgr)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = [
        d for c in contours
        if (d := _candidate(c, offset, frame_bgr.shape[1])) is not None
    ]
    # Distance is the primary priority: nearest valid disks come first.
    # Diskiness is the secondary priority, so a round candidate wins over a
    # weaker candidate at nearly the same distance. Low-diskiness lines have
    # already been removed by MIN_DISKINESS above.
    found.sort(key=lambda d: (d.distance_mm, -d.diskiness))
    return found[:MAX_DISKS]


def detections_as_json(frame_bgr: np.ndarray) -> str:
    """Return one compact JSON message for the Pi/ESP32 interface."""
    detections = detect_disks(frame_bgr)
    message = {
        "type": "disk_detections",
        "count": len(detections),
        "disks": [d.as_dict() for d in detections],
    }
    return json.dumps(message, separators=(",", ":"))


def draw_detections(frame: np.ndarray, detections: list[DiskDetection]) -> np.ndarray:
    out = frame.copy()
    for i, d in enumerate(detections, 1):
        centre = (round(d.cx_px), round(d.cy_px))
        axes = (max(round(d.major_axis_px / 2), 1), max(round(d.minor_axis_px / 2), 1))
        cv2.ellipse(out, centre, axes, d.angle_deg, 0, 360, (0, 255, 80), 2)
        cv2.circle(out, centre, 3, (0, 220, 255), -1)
        text = (
            f"{i}: d={d.distance_mm:.0f}mm "
            f"diskiness={d.diskiness:.2f} turn={d.turn_angle_deg:+.1f}°"
        )
        cv2.putText(out, text, (centre[0] - 90, max(centre[1] - 14, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 80), 1, cv2.LINE_AA)
    if any(v is not None for v in (ROI_X1, ROI_Y1, ROI_X2, ROI_Y2)):
        x1, y1 = (0 if ROI_X1 is None else ROI_X1, 0 if ROI_Y1 is None else ROI_Y1)
        x2, y2 = (FRAME_WIDTH if ROI_X2 is None else ROI_X2, FRAME_HEIGHT if ROI_Y2 is None else ROI_Y2)
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), (255, 180, 0), 1)
    return out


class Camera:
    def __init__(self) -> None:
        self.picam = None
        self.capture = None

    def open(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore
            self.picam = Picamera2()
            config = self.picam.create_preview_configuration(
                main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"}
            )
            self.picam.configure(config)
            self.picam.start()
            time.sleep(0.5)
            return
        except Exception as exc:
            print(f"Picamera2 unavailable ({exc}); trying OpenCV: {exc}")
        self.capture = cv2.VideoCapture(CAMERA_INDEX)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        if not self.capture.isOpened():
            raise RuntimeError("No usable camera found")

    def read(self) -> Optional[np.ndarray]:
        if self.picam is not None:
            return cv2.cvtColor(self.picam.capture_array(), cv2.COLOR_RGB2BGR)
        ok, frame = self.capture.read()
        return frame if ok else None

    def close(self) -> None:
        if self.picam is not None:
            self.picam.stop()
            self.picam.close()
        if self.capture is not None:
            self.capture.release()


def run_detector(preview: bool) -> None:
    camera = Camera()
    camera.open()
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue
            detections = detect_disks(frame)
            # One complete JSON object per line: easy for the Pi's decision
            # layer to consume. No robot control is performed here.
            print(detections_as_json(frame), flush=True)
            if preview:
                cv2.imshow("GALILEO disk detector", draw_detections(frame, detections))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.close()
        if preview:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    run_detector(args.preview)


if __name__ == "__main__":
    main()
