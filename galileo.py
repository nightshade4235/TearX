#!/usr/bin/env python3
#
#   Filename: crates.py
#   Authors: Joel Mathew Cinosh             | Avirbhav Dubey
#   E-mails: jademountainacademy0@gmail.com | avirbhavdubey@gmail.com
#   Iterpreter startup: python crates.py
#   Brief: The main file that orchestrates the entire robot, the robot being CR8S, the patient collection robot.
#   Date: 28-09-2026
#   Version: 1.0.2a
#   License: The MIT Lisence
#   Github URL: https://github.com/nightshade4235/TearX/blob/main/crates.py
#

"""Other Robot: black-disk image detection and distance parsing only.

This module does NOT control motors, GPIO, servos, or navigation.
It does two things:
    1. Detect up to three black disks in a camera frame.
    2. Estimate each disk's distance from its apparent major-axis diameter.

The distance estimate requires FOCAL_LENGTH_PX to be calibrated for the actual
camera, resolution, and lens configuration.
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


# =============================================================================
# CONFIGURATION MACROS
# =============================================================================

DISK_DIAMETER_MM = 56.0
DISK_THICKNESS_MM = 5.0       # Informational; not used for range calculation.
FOCAL_LENGTH_PX = 520.0       # MUST be calibrated with the actual camera.

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CAMERA_INDEX = 0

# Black-object segmentation in HSV.
HSV_S_MAX = 80
HSV_V_MAX = 60

MIN_AREA_PX = 180
MAX_AREA_PX = 80_000
MAX_AXIS_RATIO = 3.5
MIN_CIRCULARITY = 0.40
MIN_MINOR_AXIS_PX = 4.0
MIN_ELLIPSE_FILL = 0.40
MAX_ELLIPSE_FILL = 1.40
MAX_DISKS = 3

MORPH_KERNEL_SIZE = 5
MORPH_OPEN_ITERATIONS = 1
MORPH_CLOSE_ITERATIONS = 2


@dataclass(frozen=True)
class DiskDetection:
    """One detected disk and its derived distance."""

    cx_px: float
    cy_px: float
    width_px: float
    height_px: float
    major_axis_px: float
    minor_axis_px: float
    angle_deg: float
    angular_size_rad: float
    distance_mm: float

    def as_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# DISTANCE PARSER
# =============================================================================


def angular_size_from_pixels(pixel_size: float, focal_length_px: float) -> float:
    """Convert an apparent object size in pixels to angular size in radians."""
    if pixel_size <= 0 or focal_length_px <= 0:
        raise ValueError("pixel_size and focal_length_px must be positive")
    return 2.0 * math.atan(pixel_size / (2.0 * focal_length_px))


def distance_from_angular_size(real_size_mm: float, angular_size_rad: float) -> float:
    """Apply real_size = 2 * distance * tan(angle / 2)."""
    if real_size_mm <= 0 or angular_size_rad <= 0:
        raise ValueError("real_size_mm and angular_size_rad must be positive")
    denominator = 2.0 * math.tan(angular_size_rad / 2.0)
    if denominator <= 1e-12:
        return float("inf")
    return real_size_mm / denominator


def parse_distance(pixel_diameter: float) -> float:
    """Return the estimated disk distance in millimetres from pixel diameter."""
    angle = angular_size_from_pixels(pixel_diameter, FOCAL_LENGTH_PX)
    return distance_from_angular_size(DISK_DIAMETER_MM, angle)


# =============================================================================
# IMAGE PROCESSING
# =============================================================================


def black_mask(frame_bgr: np.ndarray) -> np.ndarray:
    """Create a cleaned binary mask for dark, low-saturation objects."""
    if frame_bgr is None or frame_bgr.ndim != 3:
        raise ValueError("Expected a BGR image with shape (height, width, 3)")

    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 0, 0], dtype=np.uint8)
    upper = np.array([179, HSV_S_MAX, HSV_V_MAX], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    kernel_size = max(3, int(MORPH_KERNEL_SIZE) | 1)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, kernel, iterations=MORPH_OPEN_ITERATIONS
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, kernel, iterations=MORPH_CLOSE_ITERATIONS
    )
    return mask


def _screen_dimensions(
    contour: np.ndarray,
    major_axis_px: float,
    minor_axis_px: float,
    angle_deg: float,
) -> tuple[float, float]:
    """Return vertical and horizontal bounding-box dimensions in pixels."""
    _x, _y, width, height = cv2.boundingRect(contour)
    if width > 0 and height > 0:
        return float(height), float(width)

    angle = math.radians(angle_deg)
    height = abs(major_axis_px * math.sin(angle)) + abs(
        minor_axis_px * math.cos(angle)
    )
    width = abs(major_axis_px * math.cos(angle)) + abs(
        minor_axis_px * math.sin(angle)
    )
    return float(height), float(width)


def _candidate_from_contour(contour: np.ndarray) -> Optional[DiskDetection]:
    area = cv2.contourArea(contour)
    if not (MIN_AREA_PX <= area <= MAX_AREA_PX) or len(contour) < 5:
        return None

    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 1.0:
        return None

    circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    if circularity < MIN_CIRCULARITY:
        return None

    (cx, cy), (axis_a, axis_b), angle_deg = cv2.fitEllipse(contour)
    major = max(float(axis_a), float(axis_b))
    minor = min(float(axis_a), float(axis_b))
    if minor < MIN_MINOR_AXIS_PX or major / minor > MAX_AXIS_RATIO:
        return None

    ellipse_area = math.pi * (major / 2.0) * (minor / 2.0)
    fill_ratio = area / ellipse_area if ellipse_area > 0 else 0.0
    if not (MIN_ELLIPSE_FILL <= fill_ratio <= MAX_ELLIPSE_FILL):
        return None

    # For a circular disk viewed at an angle, the projected major axis is the
    # disk diameter. The minor axis changes with tilt and is not used for range.
    angular_size = angular_size_from_pixels(major, FOCAL_LENGTH_PX)
    distance_mm = distance_from_angular_size(DISK_DIAMETER_MM, angular_size)
    height_px, width_px = _screen_dimensions(contour, major, minor, angle_deg)

    return DiskDetection(
        cx_px=float(cx),
        cy_px=float(cy),
        width_px=width_px,
        height_px=height_px,
        major_axis_px=major,
        minor_axis_px=minor,
        angle_deg=float(angle_deg),
        angular_size_rad=float(angular_size),
        distance_mm=float(distance_mm),
    )


def detect_disks(frame_bgr: np.ndarray) -> list[DiskDetection]:
    """Detect, filter, and left-to-right sort up to MAX_DISKS disks."""
    mask = black_mask(frame_bgr)
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    detections = []
    for contour in contours:
        candidate = _candidate_from_contour(contour)
        if candidate is not None:
            detections.append(candidate)

    # Keep the largest candidates, then return them in screen order.
    detections.sort(key=lambda disk: disk.major_axis_px, reverse=True)
    detections = detections[:MAX_DISKS]
    detections.sort(key=lambda disk: disk.cx_px)
    return detections


def detections_as_json(frame_bgr: np.ndarray) -> str:
    """Return detections as a JSON array for another program to consume."""
    return json.dumps(
        [disk.as_dict() for disk in detect_disks(frame_bgr)],
        separators=(",", ":"),
    )


# =============================================================================
# OPTIONAL CAMERA INPUT AND PREVIEW
# =============================================================================

class Camera:
    """Pi Camera 2 input with OpenCV fallback for a USB camera."""

    def __init__(self) -> None:
        self._picam = None
        self._capture = None

    def open(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore

            self._picam = Picamera2()
            config = self._picam.create_preview_configuration(
                main={
                    "size": (FRAME_WIDTH, FRAME_HEIGHT),
                    "format": "RGB888",
                }
            )
            self._picam.configure(config)
            self._picam.start()
            time.sleep(0.3)
            return
        except Exception as exc:
            print(f"Picamera2 unavailable ({exc}); trying OpenCV camera: {exc}")

        self._capture = cv2.VideoCapture(CAMERA_INDEX)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        if not self._capture.isOpened():
            raise RuntimeError("No usable camera found")

    def read(self) -> Optional[np.ndarray]:
        if self._picam is not None:
            rgb = self._picam.capture_array()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        if self._capture is None:
            return None
        ok, frame = self._capture.read()
        return frame if ok else None

    def close(self) -> None:
        if self._picam is not None:
            self._picam.stop()
            self._picam.close()
        if self._capture is not None:
            self._capture.release()


def draw_detections(
    frame_bgr: np.ndarray,
    detections: list[DiskDetection],
) -> np.ndarray:
    """Draw detection overlays without changing the input frame."""
    output = frame_bgr.copy()
    for index, disk in enumerate(detections, start=1):
        centre = (round(disk.cx_px), round(disk.cy_px))
        axes = (
            max(round(disk.major_axis_px / 2), 1),
            max(round(disk.minor_axis_px / 2), 1),
        )
        cv2.ellipse(
            output,
            centre,
            axes,
            disk.angle_deg,
            0,
            360,
            (0, 255, 80),
            2,
        )
        cv2.circle(output, centre, 3, (0, 220, 255), -1)
        label = (
            f"{index}: x={disk.cx_px:.0f} y={disk.cy_px:.0f} "
            f"d={disk.distance_mm:.0f}mm"
        )
        cv2.putText(
            output,
            label,
            (centre[0] - 80, max(centre[1] - 14, 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 80),
            1,
            cv2.LINE_AA,
        )
    return output


def run_detector(show_preview: bool = False) -> None:
    """Run the camera detector, optionally displaying an annotated preview.

    With show_preview=False this is headless and suitable for systemd.
    """
    camera = Camera()
    camera.open()
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue

            detections = detect_disks(frame)
            print(json.dumps([disk.as_dict() for disk in detections]))

            if show_preview:
                preview = draw_detections(frame, detections)
                cv2.imshow("other-robot disk vision", preview)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.close()
        if show_preview:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect black disks and parse their distances."
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show an annotated camera preview; omit for headless operation.",
    )
    args = parser.parse_args()

    # Default mode is headless so the program remains active under systemd.
    run_detector(show_preview=args.preview)


if __name__ == "__main__":
    main()

