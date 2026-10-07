#!/usr/bin/env python3
"""Robot 2 navigation baseline: disks, quarantine beams, and lab delivery.

Pi owns sensors, camera, nine Servo-HAT channels, and route decisions.
ESP32-S3 owns four motors and eight encoder signals. The V/S UART protocol
must match esp32s3_l298n_final.ino. All dimensions/angles marked CALIBRATE
must be measured after assembly.
"""
from __future__ import annotations
import argparse
import math
import time
from enum import Enum, auto

# Reuse the tested camera detector classes; keep this file beside the detector.
from galileo_disk_pi_master import CameraModel, DiscDetector, OnlineSelfTuner, open_camera

# ---------------------------- Pi GPIO macros -----------------------------
IR_S2, IR_S3, IR_S4 = 27, 22, 23       # physical 13,15,16
IR_BLACK_LEVEL = 1                     # confirmed test result: 1 = black
UART_DEVICE, UART_BAUD = "/dev/serial0", 115200
TOF_CLOSE_MM = 180                     # CALIBRATE after assembly
TOF_CORNER_MM = 120                     # CALIBRATE; front clearance
MAX_DISKS = 3
DISK_DIAMETER_M = 0.056
HALFWAY_REVERSE_MM = (1143 / 2) - 280  # 291.5 mm placeholder
GRIPPER_OFFSET_MM = 80                 # physical offset placeholder
SEARCH_TURN_MS = 140
MOTION_BURST_MS = 140

# Servo-HAT channels: confirm channel numbering and calibrate every angle.
DISK_GRAB = (0, 1, 2)
DISK_TILT = (3, 4, 5)
WALL_GRAB = (6, 7)
WALL_LIFT = 8
SERVO_ANGLES = {
    "disk_grab_open": None, "disk_grab_closed": None,
    "disk_tilt_up": None, "disk_tilt_down": None,
    "wall_grab_open": None, "wall_grab_closed": None,
    "wall_lift_up": None, "wall_lift_down": None,
}

class State(Enum):
    START_FORWARD = auto(); ENTER_QUARANTINE = auto(); SEARCH_DISK = auto()
    ALIGN_DISK = auto(); APPROACH_DISK = auto(); GRAB_DISK = auto()
    RETURN_FROM_DISK = auto(); RETURN_TO_LAB = auto(); ALIGN_LAB = auto()
    DELIVER_SAMPLES = auto(); RETURN_FOR_BEAMS = auto(); WALL_CONTACT = auto()
    PLACE_BEAMS = auto(); DONE = auto()

class UART:
    def __init__(self, device: str, baud: int, dry: bool):
        self.dry = dry; self.seq = 0; self.ser = None
        if not dry:
            import serial
            self.ser = serial.Serial(device, baud, timeout=0, write_timeout=.2)
    @staticmethod
    def frame(kind: str, seq: int, *values: object) -> bytes:
        body = ",".join([kind, str(seq), *(str(v) for v in values)])
        checksum = 0
        for b in body.encode("ascii"): checksum ^= b
        return f"<{body},{checksum:02X}>\n".encode("ascii")
    def send(self, direction: str, speed: float, duration_ms: int, distance_mm: int = 0):
        self.seq += 1
        packet = self.frame("V", self.seq, direction, f"{max(0,min(1,speed)):.3f}", duration_ms, distance_mm)
        if self.ser: self.ser.write(packet)
        print(packet.decode().strip())
        if not self.dry: time.sleep(duration_ms / 1000)
    def stop(self):
        self.seq += 1; packet = self.frame("S", self.seq)
        if self.ser: self.ser.write(packet)
        print(packet.decode().strip())
    def close(self):
        self.stop()
        if self.ser: self.ser.close()

class Hardware:
    def __init__(self, dry: bool):
        self.dry = dry; self.ir = None; self.tof = None; self.kit = None
        if dry: return
        from gpiozero import DigitalInputDevice
        self.ir = [DigitalInputDevice(p, pull_up=False) for p in (IR_S2, IR_S3, IR_S4)]
        import board, busio
        import adafruit_vl53l0x
        i2c = busio.I2C(board.SCL, board.SDA)
        self.tof = adafruit_vl53l0x.VL53L0X(i2c)
        from adafruit_servokit import ServoKit
        self.kit = ServoKit(channels=16, address=0x40)
    def all_black(self) -> bool:
        values = [int(x.value) for x in self.ir] if self.ir else [IR_BLACK_LEVEL] * 3
        result = all(v == IR_BLACK_LEVEL for v in values)
        print(f"IR S2/S3/S4={values} all_black={int(result)}")
        return result
    def tof_mm(self) -> int:
        value = int(self.tof.range) if self.tof else TOF_CLOSE_MM
        print(f"ToF={value} mm")
        return value
    def servo(self, channel: int, key: str):
        angle = SERVO_ANGLES[key]
        if angle is None: raise RuntimeError(f"Calibrate SERVO_ANGLES['{key}'] first")
        if self.kit: self.kit.servo[channel].angle = angle
        print(f"SERVO ch{channel} {key}={angle}")
    def grab_select(self, index: int):
        for i, ch in enumerate(DISK_GRAB): self.servo(ch, "disk_grab_closed" if i == index else "disk_grab_open")
        for i, ch in enumerate(DISK_TILT): self.servo(ch, "disk_tilt_down" if i == index else "disk_tilt_up")
    def walls_up(self):
        self.servo(WALL_LIFT, "wall_lift_up")
        for ch in WALL_GRAB: self.servo(ch, "wall_grab_open")
    def walls_down_and_release(self):
        self.servo(WALL_LIFT, "wall_lift_down")
        for ch in WALL_GRAB: self.servo(ch, "wall_grab_open")
    def close(self):
        for x in self.ir or []: x.close()

class Robot2:
    def __init__(self, dry=False, camera_matrix="camera.json"):
        self.dry = dry; self.hw = Hardware(dry); self.uart = UART(UART_DEVICE, UART_BAUD, dry)
        self.camera_matrix = camera_matrix; self.cap = None; self.detector = None
        self.tuner = None
        self.collected = 0
    def move(self, direction, speed=.25, ms=MOTION_BURST_MS, distance=0):
        self.uart.send(direction, speed, ms, distance)
    def turn_left_until(self, predicate, timeout_s=8):
        start = time.monotonic()
        while not predicate():
            if time.monotonic() - start > timeout_s: raise RuntimeError("turn-left timeout")
            self.move("L", .22, SEARCH_TURN_MS)
        self.uart.stop()
    def setup_camera(self):
        cam = CameraModel.from_json(self.camera_matrix) if __import__('pathlib').Path(self.camera_matrix).exists() else CameraModel(320,320,320,240,__import__('numpy').zeros(5))
        args = argparse.Namespace(smooth=5, min_area=250, min_ratio=.35, min_circularity=.45, max_area_error=.50, min_sharpness=4, reference_sharpness=80, black=70, contrast=15, max_detections=3, lock_timeout=8, lock_distance_penalty=35, diameter=DISK_DIAMETER_M, min_command_confidence=55)
        self.cap = open_camera(0, 640, 480, False, "auto", 15, 70, 3); self.detector = DiscDetector(args, cam)
        self.tuner = OnlineSelfTuner(args, "adaptive_profile.json")
    def detect(self):
        if self.cap is None: self.setup_camera()
        ok, frame = self.cap.read()
        if not ok: raise RuntimeError("camera read failed")
        hits = self.detector.find_all(frame)
        if hits and self.tuner is not None: self.tuner.observe(frame, hits[0])
        return hits, frame
    def align_and_approach(self):
        for _ in range(80):
            hits, _ = self.detect()
            if not hits: self.move("L", .18, SEARCH_TURN_MS); continue
            hit = hits[0]; angle = math.degrees(math.atan2(hit.center[0] - self.detector.camera.cx, self.detector.camera.fx))
            print(f"disk angle={angle:.1f} range={hit.range_m:.2f}m diskiness={hit.confidence/100:.2f}")
            if abs(angle) > 3: self.move("R" if angle > 0 else "L", .18, 100); continue
            if hit.range_m * 1000 <= TOF_CLOSE_MM: self.uart.stop(); return True
            self.move("F", .20, MOTION_BURST_MS)
        raise RuntimeError("disk alignment/approach timeout")
    def run(self):
        self.hw.walls_up()
        try:
            while self.collected < MAX_DISKS:
                while not self.hw.all_black(): self.move("F", .22)
                self.turn_left_until(lambda: self.hw.tof_mm() <= TOF_CLOSE_MM)
                self.move("B", .20, 250); self.move("L", .22, 500)
                self.align_and_approach()
                self.hw.grab_select(self.collected)
                time.sleep(.4); self.move("B", .22, 500)
                self.collected += 1
                print(f"collected disk {self.collected}/{MAX_DISKS}")
                if self.collected < MAX_DISKS: self.move("F", .18, GRIPPER_OFFSET_MM)
            self.move("B", .20, 500)
            self.move("B", .20, int(HALFWAY_REVERSE_MM / 1000 * 1000), HALFWAY_REVERSE_MM)
            self.move("L", .22, 500)
            while self.hw.tof_mm() > TOF_CLOSE_MM: self.move("F", .18)
            self.hw.grab_select(0); time.sleep(.3)
            self.move("B", .18, 300)
            while not self.hw.all_black(): self.move("F", .18)
            self.wall_contact_fallback()
            self.hw.walls_down_and_release(); time.sleep(.5)
        finally:
            if self.tuner is not None: self.tuner.save()
            self.uart.close()
            if self.cap: self.cap.release()
            self.hw.close()
    def wall_contact_fallback(self):
        print("WARNING: no contact switches; using slow corner-settle fallback")
        self.move("F", .10, 250)
        self.uart.stop(); time.sleep(.25)
        self.move("B", .10, 120)
        self.move("R", .10, 180)
        self.move("F", .08, 250)
        self.uart.stop()

def main():
    p = argparse.ArgumentParser(); p.add_argument("--dry-run", action="store_true"); p.add_argument("--camera-matrix", default="camera.json")
    a = p.parse_args(); Robot2(a.dry_run, a.camera_matrix).run()
if __name__ == "__main__": main()
      
