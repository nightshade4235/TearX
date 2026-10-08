#!/usr/bin/env python3
"""CR8S patient robot - Raspberry Pi master.

The Pi manages:
    - one IR array: S2/S3/S4
    - one VL53L0X on hardware I2C bus 1
    - one MPU-6050 on hardware I2C bus 1
    - one TCS34725 on software I2C bus 3
    - five direct-GPIO servo signals
    - one 28BYJ-48 through a ULN2003AN
    - camera-centering hook
    - navigation state machine

The ESP32 manages four motors and four encoders. The Pi communicates with it
through UART. No ESP32 motor GPIO mapping is included here.

Start safely in dry-run mode:
    python3 patient_pi_master.py --dry-run

Live mode requires all configured hardware and the final UART protocol:
    python3 patient_pi_master.py --live
"""

from __future__ import annotations

import argparse
import enum
import json
import math
import struct
import time
from dataclasses import dataclass
from typing import Optional

# =============================== GPIO macros ===============================
# These are BCM GPIO numbers. Physical pin numbers are in the wiring guide.
IR_S2 = 27       # Pi physical pin 13
IR_S3 = 22       # Pi physical pin 15
IR_S4 = 23       # Pi physical pin 16
IR_ACTIVE_LOW = True

RAMP_SERVO = 12              # physical pin 32, MG995
SWEEPER_SERVO = 13           # physical pin 33, MG90S
TRAPDOOR_1_SERVO = 16        # physical pin 36, SG90
TRAPDOOR_2_SERVO = 18        # physical pin 12, SG90
KIT_SERVO = 19               # physical pin 35, MG995
EXTRA_COMPARTMENT_1_SERVO = 24  # physical pin 18; confirm mechanism
EXTRA_COMPARTMENT_2_SERVO = 25  # physical pin 22; confirm mechanism

STEPPER_IN1 = 4              # physical pin 7
STEPPER_IN2 = 5              # physical pin 29
STEPPER_IN3 = 6              # physical pin 31
STEPPER_IN4 = 20             # physical pin 38

UART_DEVICE = "/dev/serial0"
UART_BAUD = 115200
UART_ACK_TIMEOUT = 0.15
UART_RETRIES = 3

# Hardware I2C: one VL53L0X + MPU-6050.
# Software I2C bus 3: TCS34725 at GPIO17/GPIO26.
MPU_ADDRESS = 0x68
TOF_ADDRESS = 0x29
COLOR_ADDRESS = 0x29
COLOR_BUS_NUMBER = 3

# =========================== calibration macros ============================
# Fill after measuring. The program will not pretend these are known.
TOF_CLOSE_MM: Optional[float] = None
TOF_ZONE_CONFIRM_SAMPLES = 3  # consecutive close readings required inside a zone
WHEEL_DIAMETER_MM: Optional[float] = None
ENCODER_COUNTS_PER_MM: Optional[float] = None

# 28BYJ-48 commonly uses 4096 half-steps at the geared output, but the drum
# must be measured. This value is deliberately a macro, not a silent fact.
STEPPER_STEPS_PER_SLOT: Optional[int] = None
STEPPER_STEP_DELAY_SEC = 0.002
STEPPER_INVERTED = False

# Servo angles are deliberately placeholders until the mechanism is measured.
SERVO_ANGLES = {
    "ramp_up": None,
    "ramp_down": None,
    "sweeper_home": None,
    "sweeper_in": None,
    "trapdoor_1_closed": None,
    "trapdoor_1_open": None,
    "trapdoor_2_closed": None,
    "trapdoor_2_open": None,
    "kit_closed": None,
    "kit_open": None,
    "extra_compartment_1_closed": None,
    "extra_compartment_1_open": None,
    "extra_compartment_2_closed": None,
    "extra_compartment_2_open": None,
}

# Colour thresholds are starting points only. Calibrate from real samples.
COLOR_MIN_CLEAR = 80
COLOR_WHITE_CLEAR = 1200
COLOR_MARGIN = 0.08
YELLOW_MIN_R = 0.35
YELLOW_MIN_G = 0.30
YELLOW_MAX_B = 0.22

# ================================ helpers =================================

def checksum(text: str) -> str:
    value = 0
    for byte in text.encode("ascii"):
        value ^= byte
    return f"{value:02X}"


def frame_message(kind: str, sequence: int, *values: object) -> bytes:
    body = ",".join([kind, str(sequence), *(str(v) for v in values)])
    return f"<{body},{checksum(body)}>\n".encode("ascii")


def classify_color(red: int, green: int, blue: int, clear: int) -> str:
    if clear < COLOR_MIN_CLEAR:
        return "too_dark"
    if clear >= COLOR_WHITE_CLEAR:
        return "white"
    total = red + green + blue
    if total <= 0:
        return "unknown"
    r, g, b = red / total, green / total, blue / total
    if r >= YELLOW_MIN_R and g >= YELLOW_MIN_G and b <= YELLOW_MAX_B:
        return "yellow"
    if r >= g + COLOR_MARGIN and r >= b + COLOR_MARGIN:
        return "red"
    if g >= r + COLOR_MARGIN and g >= b + COLOR_MARGIN:
        return "green"
    if b >= r + COLOR_MARGIN and b >= g + COLOR_MARGIN:
        return "blue"
    return "unknown"

# ================================ sensors =================================

class IRReader:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self._sensors = None
        if not dry_run:
            from gpiozero import Button
            self._sensors = [Button(pin, pull_up=True) for pin in (IR_S2, IR_S3, IR_S4)]

    def read(self) -> tuple[int, int, int]:
        if self.dry_run:
            return (0, 0, 0)
        values = []
        for sensor in self._sensors:
            electrical_active = bool(sensor.is_pressed)
            values.append(int(electrical_active if IR_ACTIVE_LOW else not electrical_active))
        return tuple(values)

    def all_black(self) -> bool:
        return self.read() == (1, 1, 1)

    def close(self):
        if self._sensors:
            for sensor in self._sensors:
                sensor.close()


class SensorSuite:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.ir = IRReader(dry_run)
        self.tof = None
        self.color = None
        self.i2c = None
        self.mpu_bus = None
        if dry_run:
            return

        import board
        import busio
        import adafruit_vl53l0x
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.tof = adafruit_vl53l0x.VL53L0X(self.i2c)

        # The TCS is intentionally on the separately configured bus 3.
        try:
            from adafruit_extended_bus import ExtendedI2C
            import adafruit_tcs34725
            self.color = adafruit_tcs34725.TCS34725(
                ExtendedI2C(COLOR_BUS_NUMBER), address=COLOR_ADDRESS
            )
        except Exception as exc:
            raise RuntimeError(
                "TCS34725 bus-3 setup failed; configure i2c-gpio and verify /dev/i2c-3"
            ) from exc

    def tof_mm(self) -> Optional[float]:
        if self.dry_run:
            return None
        value = getattr(self.tof, "range", None)
        return float(value) if value is not None else None

    def color_name(self) -> str:
        if self.dry_run:
            return "unknown"
        red, green, blue, clear = self.color.color_raw
        return classify_color(red, green, blue, clear)

    def close(self):
        self.ir.close()


def run_sensor_test(period_sec: float = 0.5):
    """Print live inputs only; never constructs or commands actuators."""
    # Reuse the already tested read-only routines. They catch and print their
    # own hardware errors, so one missing sensor does not hide the others.
    import patient_sensor_test as tester

    print("PATIENT MASTER SENSOR TEST: READ-ONLY")
    print("No motors, servos, stepper, or motor UART commands are enabled.")
    print("Press Ctrl+C to stop.\n")
    tester.scan_i2c()
    tester.camera_once()
    try:
        while True:
            print(f"\n--- sensor sample {time.strftime('%H:%M:%S')} ---")
            tester.print_ir_once()
            tester.read_tof_once()
            tester.read_color_once()
            tester.read_imu_once()
            time.sleep(period_sec)
    except KeyboardInterrupt:
        print("\nSensor test stopped.")

# ================================ servos ==================================

class ServoBank:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.servos = {}
        if not dry_run:
            from gpiozero import AngularServo
            for name, pin in {
                "ramp": RAMP_SERVO,
                "sweeper": SWEEPER_SERVO,
                "trapdoor_1": TRAPDOOR_1_SERVO,
                "trapdoor_2": TRAPDOOR_2_SERVO,
                "kit": KIT_SERVO,
                "extra_compartment_1": EXTRA_COMPARTMENT_1_SERVO,
                "extra_compartment_2": EXTRA_COMPARTMENT_2_SERVO,
            }.items():
                self.servos[name] = AngularServo(
                    pin, min_angle=0, max_angle=180,
                    initial_angle=None, min_pulse_width=0.0005,
                    max_pulse_width=0.0025,
                )

    def move(self, name: str, angle_key: str):
        angle = SERVO_ANGLES[angle_key]
        if angle is None:
            raise RuntimeError(f"Fill SERVO_ANGLES['{angle_key}'] before live operation")
        if not self.dry_run:
            self.servos[name].angle = angle
        print(f"SERVO {name} -> {angle_key} ({angle} deg)")

    def ramp_up(self): self.move("ramp", "ramp_up")
    def ramp_down(self): self.move("ramp", "ramp_down")
    def sweep_in(self): self.move("sweeper", "sweeper_in")
    def sweep_home(self): self.move("sweeper", "sweeper_home")

    def trapdoors_open(self):
        self.move("trapdoor_1", "trapdoor_1_open")
        self.move("trapdoor_2", "trapdoor_2_open")

    def trapdoors_close(self):
        self.move("trapdoor_1", "trapdoor_1_closed")
        self.move("trapdoor_2", "trapdoor_2_closed")

    def release_kits(self):
        self.move("kit", "kit_open")
        self.move("kit", "kit_closed")

    def release_extra_compartment_1(self):
        self.move("extra_compartment_1", "extra_compartment_1_open")
        self.move("extra_compartment_1", "extra_compartment_1_closed")

    def release_extra_compartment_2(self):
        self.move("extra_compartment_2", "extra_compartment_2_open")
        self.move("extra_compartment_2", "extra_compartment_2_closed")

    def close(self):
        for servo in self.servos.values():
            servo.detach()

# ================================ stepper =================================

class DrumStepper:
    # Half-step sequence for a common 28BYJ-48/ULN2003 combination.
    SEQUENCE = (
        (1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
        (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1),
    )

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.current_slot = 1
        self.outputs = None
        if not dry_run:
            from gpiozero import DigitalOutputDevice
            self.outputs = [DigitalOutputDevice(pin, initial_value=False)
                            for pin in (STEPPER_IN1, STEPPER_IN2, STEPPER_IN3, STEPPER_IN4)]

    def _write(self, pattern):
        if self.outputs:
            for output, value in zip(self.outputs, pattern):
                output.value = bool(value)

    def step(self, count: int):
        if STEPPER_STEPS_PER_SLOT is None:
            raise RuntimeError("Fill STEPPER_STEPS_PER_SLOT before live stepper operation")
        direction = -1 if count < 0 else 1
        sequence = self.SEQUENCE[::direction]
        for index in range(abs(count)):
            self._write(sequence[index % len(sequence)])
            time.sleep(STEPPER_STEP_DELAY_SEC)
        self._write((0, 0, 0, 0))

    def move_to_slot(self, target_slot: int):
        if target_slot not in (1, 2, 3, 4):
            raise ValueError("Drum slot must be 1..4")
        delta = (target_slot - self.current_slot) % 4
        print(f"DRUM slot {self.current_slot} -> {target_slot}; delta={delta}")
        if delta:
            self.step(delta * STEPPER_STEPS_PER_SLOT)
        self.current_slot = target_slot

    def close(self):
        self._write((0, 0, 0, 0))
        if self.outputs:
            for output in self.outputs:
                output.close()

# =============================== ESP32 UART ===============================

@dataclass
class EncoderPacket:
    sequence: int
    lf_c1: int
    lf_c2: int
    lr_c1: int
    lr_c2: int
    rf_c1: int
    rf_c2: int
    rr_c1: int
    rr_c2: int


class ESP32Link:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.sequence = 0
        self.port = None
        if not dry_run:
            import serial
            self.port = serial.Serial(UART_DEVICE, UART_BAUD, timeout=UART_ACK_TIMEOUT)

    def send_motor_command(self, left: float, right: float,
                           duration_ms: int = 100,
                           distance_mm: int = 0):
        """Send one short Pi-planned velocity action to the ESP32.

        The Pi chooses direction, speed, duration, and planned distance. The
        ESP32 only translates the direction into motor outputs and runs it
        for duration_ms.
        """
        self.sequence += 1
        left = max(-1.0, min(1.0, float(left)))
        right = max(-1.0, min(1.0, float(right)))
        if abs(left) < 0.02 and abs(right) < 0.02:
            kind = "S"
            packet = frame_message(kind, self.sequence)
        else:
            if left >= 0 and right >= 0:
                direction = "F"
            elif left <= 0 and right <= 0:
                direction = "B"
            elif left < 0 and right > 0:
                direction = "L"
            else:
                direction = "R"
            speed = max(abs(left), abs(right))
            packet = frame_message(
                "V", self.sequence, direction, f"{speed:.3f}",
                int(duration_ms), int(distance_mm)
            )
        if self.port:
            self.port.write(packet)
        print(f"UART TX {packet.decode().strip()}")

    def stop(self):
        self.sequence += 1
        packet = frame_message("S", self.sequence)
        if self.port:
            self.port.write(packet)
        print(f"UART TX {packet.decode().strip()}")

    def read_encoder_packet(self) -> Optional[EncoderPacket]:
        if self.dry_run or not self.port:
            return None
        line = self.port.readline().decode("ascii", errors="replace").strip()
        if not line.startswith("<E,") or not line.endswith(">"):
            return None
        try:
            body = line[1:-1]
            fields = body.split(",")
            # E,sequence,LF_C1,LF_C2,LR_C1,LR_C2,RF_C1,RF_C2,RR_C1,RR_C2,checksum
            if len(fields) != 11 or fields[0] != "E":
                return None
            expected = checksum(",".join(fields[:-1]))
            if fields[-1].upper() != expected:
                return None
            return EncoderPacket(*(int(x) for x in fields[1:10]))
        except (ValueError, IndexError):
            return None

    def close(self):
        if self.port:
            self.port.close()

# ============================= navigation =================================

class State(enum.Enum):
    START = enum.auto()
    CROSS_START_LINE = enum.auto()
    FIND_PATIENT = enum.auto()
    ALIGN_PATIENT = enum.auto()
    COLLECT_PATIENT = enum.auto()
    CROSS_MIDDLE_LANDMARK = enum.auto()
    RETURN_TURN = enum.auto()
    GO_RIGHT_PCC = enum.auto()
    DISPENSE_RIGHT_PCC = enum.auto()
    GO_LEFT_PCC = enum.auto()
    DISPENSE_LEFT_PCC = enum.auto()
    RETURN_HOME = enum.auto()
    ENTER_HOME_ZONE = enum.auto()
    FINISHED = enum.auto()
    FAULT = enum.auto()


class PatientRobot:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.sensors = SensorSuite(dry_run)
        self.servos = ServoBank(dry_run)
        self.drum = DrumStepper(dry_run)
        self.esp = ESP32Link(dry_run)
        self.state = State.START
        self.running = True
        self.last_state_time = time.monotonic()
        self.all_black_count = 0
        self.tof_close_count = 0

    def set_state(self, state: State):
        self.state = state
        self.last_state_time = time.monotonic()
        print(f"STATE -> {state.name}")

    def close_wall(self) -> bool:
        value = self.sensors.tof_mm()
        return TOF_CLOSE_MM is not None and value is not None and value <= TOF_CLOSE_MM

    def inside_destination_zone(self) -> bool:
        """Confirm the robot is actually inside a destination zone.

        A single ToF sample can be a noise spike. Require several consecutive
        readings at or below the calibrated close threshold while the robot is
        still driving into the zone. The caller stops before opening both
        trapdoors.
        """
        if self.close_wall():
            self.tof_close_count += 1
        else:
            self.tof_close_count = 0
        return self.tof_close_count >= TOF_ZONE_CONFIRM_SAMPLES

    def reset_zone_confirmation(self):
        self.tof_close_count = 0

    def all_black_confirmed(self, required=3) -> bool:
        if self.sensors.ir.all_black():
            self.all_black_count += 1
        else:
            self.all_black_count = 0
        return self.all_black_count >= required

    def drive(self, left: float, right: float):
        self.esp.send_motor_command(left, right)

    def stop(self):
        self.esp.stop()

    def collect_patient(self):
        # Camera-centering hook belongs here once camera output is defined.
        self.stop()
        self.servos.ramp_up()
        self.servos.sweep_in()
        self.servos.ramp_down()

    def dispense_yellow(self, slot: int):
        self.stop()
        self.drum.move_to_slot(slot)
        self.servos.trapdoors_open()
        self.servos.trapdoors_close()

    def dispense_green(self):
        self.stop()
        self.drum.move_to_slot(4)
        self.servos.trapdoors_open()
        self.servos.trapdoors_close()

    def dispense_red_and_kits(self):
        self.stop()
        self.drum.move_to_slot(2)
        self.servos.trapdoors_open()
        self.servos.trapdoors_close()
        self.servos.release_kits()

    def tick(self):
        """Advance one state without inventing unmeasured distances."""
        if self.state == State.START:
            # Drum is physically placed at Y1/slot 1 before startup.
            self.drum.current_slot = 1
            self.set_state(State.CROSS_START_LINE)

        elif self.state == State.CROSS_START_LINE:
            self.drive(0.25, 0.25)
            if self.all_black_confirmed():
                self.stop()
                self.set_state(State.FIND_PATIENT)

        elif self.state == State.FIND_PATIENT:
            # Exact patient-route movement is intentionally left for the
            # detailed route table. Do not guess distances here.
            self.drive(0.18, 0.18)
            if self.close_wall():
                self.set_state(State.ALIGN_PATIENT)

        elif self.state == State.ALIGN_PATIENT:
            # Camera centering and a signed correction belong here.
            self.stop()
            self.set_state(State.COLLECT_PATIENT)

        elif self.state == State.COLLECT_PATIENT:
            self.collect_patient()
            self.set_state(State.CROSS_MIDDLE_LANDMARK)

        elif self.state == State.CROSS_MIDDLE_LANDMARK:
            self.drive(0.25, 0.25)
            if self.all_black_confirmed():
                self.stop()
                self.set_state(State.RETURN_TURN)

        elif self.state == State.RETURN_TURN:
            # Exact IMU turn command must be added after navigation briefing.
            self.stop()
            self.set_state(State.GO_RIGHT_PCC)

        elif self.state == State.GO_RIGHT_PCC:
            self.drive(0.20, 0.20)
            if self.inside_destination_zone():
                self.stop()
                self.reset_zone_confirmation()
                self.set_state(State.DISPENSE_RIGHT_PCC)

        elif self.state == State.DISPENSE_RIGHT_PCC:
            self.dispense_yellow(2)
            self.set_state(State.GO_LEFT_PCC)

        elif self.state == State.GO_LEFT_PCC:
            self.drive(0.20, 0.20)
            if self.inside_destination_zone():
                self.stop()
                self.reset_zone_confirmation()
                self.set_state(State.DISPENSE_LEFT_PCC)

        elif self.state == State.DISPENSE_LEFT_PCC:
            self.dispense_red_and_kits()
            self.set_state(Stat
