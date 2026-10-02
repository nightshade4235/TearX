"""
CR8S Robot 1 - Patient and Medical-Kit Robot
==============================================

This is a hardware-safe baseline for Robot 1 only.

Robot 1 responsibilities:
    - collect and classify 12 patient cylinders
    - deliver red patients to Hospital
    - deliver yellow patients to PCC1/PCC2
    - deliver green patients to the Recovery Zone
    - deliver 6 kits to Hospital and 2 kits to each PCC

Robot 2 responsibilities, intentionally not implemented here:
    - collect the three sample disks
    - deliver disks to the laboratory
    - place the two containment beams

IMPORTANT:
    - All unknown GPIO and calibration values remain placeholders.
    - Do not run on hardware until the configuration section is completed.
    - The motor interface below assumes PWM + DIR. Verify this against the
      actual TB6612FNG wiring; a direct TB6612FNG connection usually uses
      PWM + IN1 + IN2 + STBY and would require a different Motor class.
    - Storage can be configured later as STEP/DIR, four-servo, or another
      mechanism. No mechanism is silently assumed.
"""

import math
import time

import board
import busio
import adafruit_tcs34725
import adafruit_vl53l0x

from gpiozero import Button, DigitalOutputDevice, PWMOutputDevice


# ============================================================================
# CONFIGURATION - REPLACE ONLY AFTER THE HARDWARE IS VERIFIED
# ============================================================================

WHEEL_DIAMETER_MM = 42.0
WHEEL_CIRCUMFERENCE_MM = math.pi * WHEEL_DIAMETER_MM
ENCODER_COUNTS_PER_REV = 0       # Must be measured for the N20 encoder wiring.

# Motor interface placeholders: PWM + DIR.
LEFT_FRONT_PWM_PIN = None
LEFT_FRONT_DIR_PIN = None
LEFT_FRONT_ENCODER_A_PIN = None
LEFT_FRONT_ENCODER_B_PIN = None  # Optional until quadrature wiring is confirmed.

LEFT_REAR_PWM_PIN = None
LEFT_REAR_DIR_PIN = None
LEFT_REAR_ENCODER_A_PIN = None
LEFT_REAR_ENCODER_B_PIN = None

RIGHT_FRONT_PWM_PIN = None
RIGHT_FRONT_DIR_PIN = None
RIGHT_FRONT_ENCODER_A_PIN = None
RIGHT_FRONT_ENCODER_B_PIN = None

RIGHT_REAR_PWM_PIN = None
RIGHT_REAR_DIR_PIN = None
RIGHT_REAR_ENCODER_A_PIN = None
RIGHT_REAR_ENCODER_B_PIN = None

LEFT_IR_PINS = []
RIGHT_IR_PINS = []
IR_ACTIVE_HIGH = True          # Verify with the actual IR boards.

TOF_FRONT_XSHUT_PIN = None
TOF_SIDE_XSHUT_PIN = None
TOF_FRONT_ADDRESS = 0x30
TOF_SIDE_ADDRESS = 0x31

ESTOP_PIN = None

# Choose only after the physical storage mechanism is confirmed.
STORAGE_MODE = None            # "stepper", "servo", or another implemented mode.

# Optional stepper storage configuration.
STORAGE_STEP_PIN = None
STORAGE_DIR_PIN = None
STORAGE_HOME_PIN = None
STORAGE_STEPS_PER_REV = 0

# Optional four-servo storage configuration.
STORAGE_PICKUP_SERVO_PIN = None
STORAGE_SORT_SERVO_PIN = None
STORAGE_ROTATION_SERVO_PIN = None
STORAGE_RELEASE_SERVO_PIN = None

# Servo positions are deliberately uncalibrated placeholders.
PICKUP_UP_POSITION = None
PICKUP_DOWN_POSITION = None
SORT_POSITION_RED = None
SORT_POSITION_YELLOW_1 = None
SORT_POSITION_YELLOW_2 = None
SORT_POSITION_GREEN = None
RELEASE_CLOSED_POSITION = None
RELEASE_OPEN_POSITION = None

# Route distances are deliberately empty until measured on the actual board.
PATIENT_LEG_DISTANCES_MM = []

MOTOR_PWM_FREQUENCY_HZ = 1000
DEFAULT_FORWARD_SPEED = 0.35
DEFAULT_REVERSE_SPEED = 0.30
MAX_MOTOR_SPEED = 0.70

COMPETITION_TIME_LIMIT_SEC = 120.0
MAX_MOVEMENT_TIME_SEC = 8.0
LINE_TIMEOUT_SEC = 8.0
TOF_TIMEOUT_SEC = 3.0
WALL_STOP_DISTANCE_MM = 100
LINE_DEBOUNCE_COUNT = 3
LINE_RETRIES = 3
WALL_RETRIES = 3

COLOR_SAMPLES = 5
COLOR_SAMPLE_DELAY_SEC = 0.02
COLOR_RETRIES = 5
COLOR_INTEGRATION_TIME = 50
COLOR_GAIN = 4

DRUM_SLOTS = 4
SLOT_RED = 1
SLOT_YELLOW_PCC1 = 2
SLOT_GREEN = 3
SLOT_YELLOW_PCC2 = 4

PATIENT_COUNT = 12
KIT_COUNT = 10


# ============================================================================
# GLOBAL STATE AND VALIDATION
# ============================================================================

MISSION_START_TIME = None
SAFETY_STOP = False


def require_configuration():
    motor_values = [
        LEFT_FRONT_PWM_PIN, LEFT_FRONT_DIR_PIN, LEFT_FRONT_ENCODER_A_PIN,
        LEFT_REAR_PWM_PIN, LEFT_REAR_DIR_PIN, LEFT_REAR_ENCODER_A_PIN,
        RIGHT_FRONT_PWM_PIN, RIGHT_FRONT_DIR_PIN, RIGHT_FRONT_ENCODER_A_PIN,
        RIGHT_REAR_PWM_PIN, RIGHT_REAR_DIR_PIN, RIGHT_REAR_ENCODER_A_PIN,
    ]

    required = motor_values + [
        TOF_FRONT_XSHUT_PIN,
        TOF_SIDE_XSHUT_PIN,
        ESTOP_PIN,
    ]

    if any(value is None for value in required):
        raise RuntimeError("Motor, encoder, ToF, or E-stop GPIO is unconfigured")

    if not LEFT_IR_PINS or not RIGHT_IR_PINS:
        raise RuntimeError("IR sensor GPIO arrays are unconfigured")

    if ENCODER_COUNTS_PER_REV <= 0:
        raise RuntimeError("ENCODER_COUNTS_PER_REV must be measured and configured")

    if STORAGE_MODE not in {"stepper", "servo"}:
        raise RuntimeError("STORAGE_MODE must be configured as 'stepper' or 'servo'")

    if STORAGE_MODE == "stepper":
        values = [STORAGE_STEP_PIN, STORAGE_DIR_PIN, STORAGE_HOME_PIN]
        if any(value is None for value in values) or STORAGE_STEPS_PER_REV <= 0:
            raise RuntimeError("Stepper storage configuration is incomplete")

    if STORAGE_MODE == "servo":
        values = [
            STORAGE_PICKUP_SERVO_PIN,
            STORAGE_SORT_SERVO_PIN,
            STORAGE_ROTATION_SERVO_PIN,
            STORAGE_RELEASE_SERVO_PIN,
        ]
        if any(value is None for value in values):
            raise RuntimeError("Servo storage GPIO configuration is incomplete")


# ============================================================================
# SAFETY
# ============================================================================

class SafetyController:
    def __init__(self):
        self.estop = Button(ESTOP_PIN, pull_up=True)
        self.estop.when_pressed = self.trigger

    def trigger(self):
        global SAFETY_STOP
        SAFETY_STOP = True

    def check(self):
        if SAFETY_STOP:
            raise RuntimeError("Software emergency stop is active")

        if self.estop.is_pressed:
            raise RuntimeError("Emergency stop is pressed")

        if MISSION_START_TIME is not None:
            elapsed = time.monotonic() - MISSION_START_TIME
            if elapsed >= COMPETITION_TIME_LIMIT_SEC:
                raise RuntimeError("Competition time limit exceeded")


# ============================================================================
# ENCODERS AND MOTORS
# ============================================================================

class Encoder:
    """Single-edge counter baseline; add verified quadrature decoding later."""

    def __init__(self, pin_a, pin_b=None):
        self.count = 0
        self.sensor_a = Button(pin_a, pull_up=True)
        self.sensor_a.when_pressed = self.increment
        self.sensor_b = None
        # B is retained as a configuration placeholder. Direction decoding is
        # intentionally not guessed until the N20 encoder wiring is verified.
        if pin_b is not None:
            self.sensor_b = Button(pin_b, pull_up=True)

    def increment(self):
        self.count += 1

    def reset(self):
        self.count = 0

    def distance_mm(self):
        revolutions = self.count / ENCODER_COUNTS_PER_REV
        return revolutions * WHEEL_CIRCUMFERENCE_MM


class Motor:
    def __init__(self, pwm_pin, direction_pin, encoder_a_pin, encoder_b_pin, safety):
        self.safety = safety
        self.pwm = PWMOutputDevice(
            pwm_pin,
            frequency=MOTOR_PWM_FREQUENCY_HZ,
            initial_value=0,
        )
        self.direction = DigitalOutputDevice(direction_pin, initial_value=False)
        self.encoder = Encoder(encoder_a_pin, encoder_b_pin)

    def set(self, speed):
        self.safety.check()
        speed = max(-MAX_MOTOR_SPEED, min(MAX_MOTOR_SPEED, speed))

        if speed >= 0:
            self.direction.on()
            self.pwm.value = speed
        else:
            self.direction.off()
            self.pwm.value = abs(speed)

    def stop(self):
        self.pwm.value = 0

    def reset_encoder(self):
        self.encoder.reset()

    def distance_mm(self):
        return self.encoder.distance_mm()


class DriveSystem:
    def __init__(self, safety):
        self.left_front = Motor(
            LEFT_FRONT_PWM_PIN, LEFT_FRONT_DIR_PIN,
            LEFT_FRONT_ENCODER_A_PIN, LEFT_FRONT_ENCODER_B_PIN, safety
        )
        self.left_rear = Motor(
            LEFT_REAR_PWM_PIN, LEFT_REAR_DIR_PIN,
            LEFT_REAR_ENCODER_A_PIN, LEFT_REAR_ENCODER_B_PIN, safety
        )
        self.right_front = Motor(
            RIGHT_FRONT_PWM_PIN, RIGHT_FRONT_DIR_PIN,
            RIGHT_FRONT_ENCODER_A_PIN, RIGHT_FRONT_ENCODER_B_PIN, safety
        )
        self.right_rear = Motor(
            RIGHT_REAR_PWM_PIN, RIGHT_REAR_DIR_PIN,
            RIGHT_REAR_ENCODER_A_PIN, RIGHT_REAR_ENCODER_B_PIN, safety
        )

    def set(self, left_speed, right_speed):
        self.left_front.set(left_speed)
        self.left_rear.set(left_speed)
        self.right_front.set(right_speed)
        self.right_rear.set(right_speed)

    def forward(self, speed=DEFAULT_FORWARD_SPEED):
        self.set(abs(speed), abs(speed))

    def reverse(self, speed=DEFAULT_REVERSE_SPEED):
        self.set(-abs(speed), -abs(speed))

    def turn_left(self, speed=0.30):
        self.set(-abs(speed), abs(speed))

    def turn_right(self, speed=0.30):
        self.set(abs(speed), -abs(speed))

    def stop(self):
        for motor in (
            self.left_front, self.left_rear,
            self.right_front, self.right_rear,
        ):
            motor.stop()

    def reset_encoders(self):
        for motor in (
            self.left_front, self.left_rear,
            self.right_front, self.right_rear,
        ):
            motor.reset_encoder()

    def left_distance(self):
        return (
            self.left_front.distance_mm() + self.left_rear.distance_mm()
        ) / 2.0

    def right_distance(self):
        return (
            self.right_front.distance_mm() + self.right_rear.distance_mm()
        ) / 2.0

    def distance(self):
        return (self.left_distance() + self.right_distance()) / 2.0


# ============================================================================
# SENSORS
# ============================================================================

class LineSensors:
    def __init__(self):
        self.left = [Button(pin, pull_up=True) for pin in LEFT_IR_PINS]
        self.right = [Button(pin, pull_up=True) for pin in RIGHT_IR_PINS]

    def _value(self, sensor):
        value = sensor.is_pressed
        return value if IR_ACTIVE_HIGH else not value

    def left_values(self):
        return [self._value(sensor) for sensor in self.left]

    def right_values(self):
        return [self._value(sensor) for sensor in self.right]

    def all_high(self):
        values = self.left_values() + self.right_values()
        return bool(values) and all(values)


class ToFSensors:
    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.front_shutdown = DigitalOutputDevice(TOF_FRONT_XSHUT_PIN, initial_value=False)
        self.side_shutdown = DigitalOutputDevice(TOF_SIDE_XSHUT_PIN, initial_value=False)
        self.front = None
        self.side = None
        self._setup_unique_addresses()

    def _setup_unique_addresses(self):
        self.front_shutdown.off()
        self.side_shutdown.off()
        time.sleep(0.1)

        self.front_shutdown.on()
        time.sleep(0.1)
        self.front = adafruit_vl53l0x.VL53L0X(self.i2c)
        self.front.set_address(TOF_FRONT_ADDRESS)

        self.side_shutdown.on()
        time.sleep(0.1)
        self.side = adafruit_vl53l0x.VL53L0X(self.i2c)
        self.side.set_address(TOF_SIDE_ADDRESS)

    def front_mm(self):
        try:
            return self.front.range
        except Exception:
            return None

    def side_mm(self):
        try:
            return self.side.range
        except Exception:
            return None


class ColorSensor:
    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.sensor = adafruit_tcs34725.TCS34725(self.i2c)
        self.sensor.integration_time = COLOR_INTEGRATION_TIME
        self.sensor.gain = COLOR_GAIN

    def read(self):
        red = green = blue = 0.0

        for _ in range(COLOR_SAMPLES):
            r, g, b, _ = self.sensor.color_raw()
            red += r
            green += g
            blue += b
            time.sleep(COLOR_SAMPLE_DELAY_SEC)

        total = red + green + blue
        if total <= 0:
            return None

        r, g, b = red / total, green / total, blue / total

        # Starting thresholds only. Calibrate with the real cylinders and light.
        if r > 0.42 and r > g * 1.25 and r > b * 1.35:
            return "red"
        if r > 0.30 and g > 0.30 and b < 0.20:
            return "yellow"
        if g > 0.40 and g > r * 1.15 and g > b * 1.20:
            return "green"
        return None


# ============================================================================
# STORAGE ABSTRACTION
# ============================================================================

class StorageSystem:
    """Interface for the actual pickup, sorting, storage, and release hardware."""

    def collect_patient(self):
        raise NotImplementedError

    def store_patient(self, slot):
        raise NotImplementedError

    def release_slot(self, slot):
        raise NotImplementedError

    def load_kits(self):
        raise NotImplementedError


class StepperStorage(StorageSystem):
    """Optional 28BYJ-48/ULN2003 implementation, pending mechanism verification."""

    SEQUENCE = (
        (1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
        (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1),
    )

    def __init__(self, safety):
        self.safety = safety
        self.step = DigitalOutputDevice(STORAGE_STEP_PIN)
        self.direction = DigitalOutputDevice(STORAGE_DIR_PIN)
        self.home = Button(STORAGE_HOME_PIN, pull_up=True)
        self.current_slot = SLOT_RED

    def home_storage(self):
        start = time.monotonic()
        while not self.home.is_pressed:
            self.safety.check()
            if time.monotonic() - start > 10.0:
                self.release_outputs()
                raise RuntimeError("Storage homing timeout")
            self.direction.off()
            self.step.on()
            time.sleep(0.001)
            self.step.off()
            time.sleep(0.001)
        self.current_slot = SLOT_RED
        self.release_outputs()

    def release_outputs(self):
        self.step.off()

    def collect_patient(self):
        pass

    def store_patient(self, slot):
        if slot not in (SLOT_RED, SLOT_YELLOW_PCC1, SLOT_GREEN, SLOT_YELLOW_PCC2):
            raise ValueError("Invalid storage slot")
        # Step count and physical slot order still require calibration.
        self.current_slot = slot

    def release_slot(self, slot):
        self.store_patient(slot)

    def load_kits(self):
        pass


class ServoStorage(StorageSystem):
    """Placeholder for the four-servo mechanism shown in the block diagram."""

    def __init__(self, safety):
        self.safety = safety
        raise NotImplementedError(
            "ServoStorage needs verified servo positions and mechanism behavior"
        )


# ============================================================================
# NAVIGATION
# ============================================================================

class Navigation:
    def __init__(self, drive, lines, tof, safety):
        self.drive = drive
        self.lines = lines
        self.tof = tof
        self.safety = safety

    def line_checkpoint(self):
        for attempt in range(LINE_RETRIES):
            start = time.monotonic()
            high_count = 0

            while time.monotonic() - start < LINE_TIMEOUT_SEC:
                self.safety.check()
                if self.lines.all_high():
                    high_count += 1
                    if high_count >= LINE_DEBOUNCE_COUNT:
                        self.drive.stop()
                        self.drive.reset_encoders()
                        return True
                else:
                    high_count = 0

                self.drive.forward()
                time.sleep(0.005)

            self.drive.stop()
            if attempt < LINE_RETRIES - 1:
                self.drive.forward(0.15)
                time.sleep(0.20)
                self.drive.stop()

        raise RuntimeError("Line checkpoint failed after retries")

    def wall_checkpoint(self):
        for attempt in range(WALL_RETRIES):
            start = time.monotonic()

            while time.monotonic() - start < TOF_TIMEOUT_SEC:
                self.safety.check()
                distance = self.tof.front_mm()

                if distance is None:
                    self.drive.stop()
                    time.sleep(0.05)
                    continue

                if distance <= WALL_STOP_DISTANCE_MM:
                    self.drive.stop()
                    self.drive.reset_encoders()
                    return True

                self.drive.forward(0.25)
                time.sleep(0.01)

            self.drive.stop()
            if attempt < WALL_RETRIES - 1:
                time.sleep(0.15)

        raise RuntimeError("Wall checkpoint failed after retries")

    def drive_distance(self, distance_mm, speed=DEFAULT_FORWARD_SPEED):
        if distance_mm == 0:
            self.drive.stop()
            return True

        direction = 1 if distance_mm > 0 else -1
        target = abs(distance_mm)
        speed = abs(speed)
        self.drive.reset_encoders()
        start = time.monotonic()

        while self.drive.distance() < target:
            self.safety.check()
            if time.monotonic() - start > MAX_MOVEMENT_TIME_SEC:
                self.drive.stop()
                raise RuntimeError("Drive-distance timeout")

            left = self.drive.left_distance()
            right = self.drive.right_distance()
            correction = (left - right) * 0.01
            left_speed = max(0.0, min(MAX_MOTOR_SPEED, speed - correction))
            right_speed = max(0.0, min(MAX_MOTOR_SPEED, speed + correction))
            self.drive.set(direction * left_speed, direction * right_speed)
            time.sleep(0.005)

        self.drive.stop()
        self.drive.reset_encoders()
        return True

    def turn_by_time(self, direction, seconds, speed=0.25):
        """Temporary fallback only; replace with verified IMU/encoder turning."""
        if seconds <= 0:
            raise ValueError("Turn duration must be positive")

        start = time.monotonic()
        while time.monotonic() - start < seconds:
            self.safety.check()
            if direction == "left":
                self.drive.turn_left(speed)
            elif direction == "right":
                self.drive.turn_right(speed)
            else:
                raise ValueError("direction must be 'left' or 'right'")
            time.sleep(0.01)
        self.drive.stop()


# ============================================================================
# ROBOT 1 MISSION CONTROLLER
# ============================================================================

class PatientRobot:
    def __init__(self):
        global MISSION_START_TIME
        require_configuration()

        self.safety = SafetyController()
        self.drive = DriveSystem(self.safety)
        self.lines = LineSensors()
        self.tof = ToFSensors()
        self.color = ColorSensor()
        self.navigation = Navigation(self.drive, self.lines, self.tof, self.safety)

        if STORAGE_MODE == "stepper":
            self.storage = StepperStorage(self.safety)
        else:
            self.storage = ServoStorage(self.safety)

        self.patient_count = 0
        self.yellow_toggle = 0
        self.kits_remaining = KIT_COUNT
        MISSION_START_TIME = None

    def slot_for_color(self, color):
        if color == "red":
            return SLOT_RED
        if color == "green":
            return SLOT_GREEN
        if color == "yellow":
            slot = SLOT_YELLOW_PCC1 if self.yellow_toggle == 0 else SLOT_YELLOW_PCC2
            self.yellow_toggle = 1 - self.yellow_toggle
            return slot
        return None

    def identify_patient(self):
        for _ in range(COLOR_RETRIES):
            self.safety.check()
            color = self.color.read()
            if color is not None:
                return color
            time.sleep(0.05)
        raise RuntimeError("Unable to identify patient color")

    def collect_patient(self):
        self.safety.check()
        self.storage.collect_patient()
        color = self.identify_patient()
        slot = self.slot_for_color(color)
        if slot is None:
            raise RuntimeError("Invalid patient color")
        self.storage.store_patient(slot)
        self.patient_count += 1
        print(f"Patient {self.patient_count}: {color} -> slot {slot}")

    def load_medical_kits(self):
        self.storage.load_kits()
        self.kits_remaining = KIT_COUNT

    def deliver_slot(self, slot, kit_count):
        if kit_count < 0 or kit_count > self.kits_remaining:
            raise ValueError("Invalid medical-kit count")
        self.storage.release_slot(slot)
        self.kits_remaining -= kit_count

    def collect_patients_on_configured_route(self):
        if len(PATIENT_LEG_DISTANCES_MM) != PATIENT_COUNT:
            raise RuntimeError(
                "PATIENT_LEG_DISTANCES_MM must contain 12 measured route legs"
            )

        for distance_mm in PATIENT_LEG_DISTANCES_MM:
            self.navigation.drive_distance(distance_mm)
            self.collect_patient()

    def run(self):
        global MISSION_START_TIME
        try:
            MISSION_START_TIME = time.monotonic()
            self.load_medical_kits()
            self.collect_patients_on_configured_route()
            raise NotImplementedError(
                "Final PCC/Hospital/Recovery routes and release actions must be measured"
            )
        finally:
            self.drive.stop()
            if hasattr(self.storage, "release_outputs"):
                self.storage.release_outputs()


def main():
    robot = None
    try:
        robot = PatientRobot()
        robot.run()
    except KeyboardInterrupt:
        print("Keyboard interrupt")
    except Exception as error:
        print(f"CR8S stopped safely: {error}")
    finally:
        if robot is not None:
            robot.drive.stop()
            if hasattr(robot.storage, "release_outputs"):
                robot.storage.release_outputs()


if __name__ == "__main__":
    main()
