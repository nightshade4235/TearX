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

"""
CR8S - Patient Collection Robot
================================

IMPORTANT:
This is the FIRST HARDWARE/CONTROL VERSION.

The GPIO assignments below are ASSUMPTIONS for testing.
Change them after the actual wiring is finalized.

The program is intentionally conservative:
    - Motors are stopped on exceptions.
    - A watchdog stops the robot if a control loop stalls.
    - Movement has timeouts.
    - The drum has a homing procedure.
    - The emergency stop is checked frequently.
    - Sensor failures do not silently command the robot forward.
    - The Raspberry Pi GPIO is NEVER used to power motors directly.

Hardware assumptions:
    Raspberry Pi 4/5
    4x DC geared motors with quadrature encoders
    4x motor-driver channels
    2x IR arrays
    2x VL53L0X ToF sensors
    1x TCS34725 color sensor
    1x IMU
    1x 28BYJ-48 5V stepper
    1x ULN2003 stepper driver
    1x pickup servo
    1x trapdoor servo
    1x physical emergency-stop input

WARNING:
This software does NOT replace a physical emergency-stop circuit.

For competition hardware, the safest design is:
    battery -> fuse -> physical E-stop -> motor power
                                 |
                                 +-> Raspberry Pi
                                     (through appropriate regulator)

The software E-stop below is an additional safety layer.
"""


# ============================================================================
# IMPORTS
# ============================================================================

import time
import math
import threading

import board
import busio

import adafruit_tcs34725
import adafruit_vl53l0x

from gpiozero import (
    PWMOutputDevice,
    DigitalOutputDevice,
    DigitalInputDevice,
    Button,
    Servo
)


# ============================================================================
# CONFIGURATION
# ============================================================================
#
# These constants are intentionally grouped here.
#
# Think of this section as the Python equivalent of C/C++ #define statements.
#
# If you change a wire:
#
#     LEFT_FRONT_PWM_PIN = 12
#
# you should NOT have to search the entire program for GPIO 12.
#
# IMPORTANT:
# GPIO NUMBERS BELOW ARE BCM GPIO NUMBERS, NOT PHYSICAL HEADER PIN NUMBERS.
#
# ============================================================================


# --------------------------------------------------------------------------
# SOFTWARE VERSION
# --------------------------------------------------------------------------

CR8S_SOFTWARE_VERSION = "1.0.3a"


# --------------------------------------------------------------------------
# WHEEL / ENCODER CONFIGURATION
# --------------------------------------------------------------------------

WHEEL_DIAMETER_MM = 42.0

WHEEL_CIRCUMFERENCE_MM = (
    math.pi * WHEEL_DIAMETER_MM
)

# CHANGE THIS AFTER TESTING THE ACTUAL MOTORS.
#
# This must represent the number of encoder pulses counted for ONE
# wheel revolution with the way your encoder is wired/configured.
#
# DO NOT GUESS THIS FOR FINAL COMPETITION SOFTWARE.
ENCODER_COUNTS_PER_REV = 20


# --------------------------------------------------------------------------
# MOTOR GPIO
# --------------------------------------------------------------------------
#
# Assumed motor-driver interface:
#
#     PWM pin       -> speed
#     DIR pin       -> direction
#
# This is only an example.
#
# If your motor driver has IN1/IN2/PWM instead, the Motor class will need
# to be changed.
# --------------------------------------------------------------------------

LEFT_FRONT_PWM_PIN = 12
LEFT_FRONT_DIR_PIN = 5
LEFT_FRONT_ENCODER_PIN = 6

LEFT_REAR_PWM_PIN = 13
LEFT_REAR_DIR_PIN = 16
LEFT_REAR_ENCODER_PIN = 20

RIGHT_FRONT_PWM_PIN = 18
RIGHT_FRONT_DIR_PIN = 23
RIGHT_FRONT_ENCODER_PIN = 24

RIGHT_REAR_PWM_PIN = 19
RIGHT_REAR_DIR_PIN = 25
RIGHT_REAR_ENCODER_PIN = 26


# --------------------------------------------------------------------------
# MOTOR SETTINGS
# --------------------------------------------------------------------------

MOTOR_PWM_FREQUENCY_HZ = 1000

DEFAULT_FORWARD_SPEED = 0.35
DEFAULT_REVERSE_SPEED = 0.30

MAX_MOTOR_SPEED = 0.70

# Never allow the robot to sit in a movement loop forever.
MAX_MOVEMENT_TIME_SEC = 8.0


# --------------------------------------------------------------------------
# IR SENSOR GPIO
# --------------------------------------------------------------------------
#
# Replace these with the actual outputs of your two IR arrays.
#
# Example assumes each array has four digital outputs.
#
# You may have 5, 6, 8, etc. sensors per array.
# Change the arrays accordingly.
# --------------------------------------------------------------------------

LEFT_IR_PINS = [
    17,
    27,
    22,
    10
]

RIGHT_IR_PINS = [
    9,
    11,
    8,
    7
]


# --------------------------------------------------------------------------
# TOF XSHUT PINS
# --------------------------------------------------------------------------
#
# Two VL53L0X sensors normally start at the same I2C address.
#
# XSHUT lets us:
#
#     1. Turn sensor A on.
#     2. Give it a new I2C address.
#     3. Turn sensor B on.
#     4. Give it another address.
#
# These pins are NOT the I2C SDA/SCL pins.
# --------------------------------------------------------------------------

TOF_FRONT_XSHUT_PIN = 4
TOF_SIDE_XSHUT_PIN = 14

TOF_FRONT_ADDRESS = 0x30
TOF_SIDE_ADDRESS = 0x31

WALL_STOP_DISTANCE_MM = 100

TOF_TIMEOUT_SEC = 3.0


# --------------------------------------------------------------------------
# I2C
# --------------------------------------------------------------------------

# Raspberry Pi hardware I2C:
#
# SDA = GPIO 2
# SCL = GPIO 3
#
# We don't need to configure those as GPIO outputs ourselves.
I2C_SDA = board.SDA
I2C_SCL = board.SCL


# --------------------------------------------------------------------------
# COLOR SENSOR
# --------------------------------------------------------------------------

COLOR_SAMPLES = 5
COLOR_SAMPLE_DELAY_SEC = 0.02

COLOR_RETRY_COUNT = 5

COLOR_SENSOR_INTEGRATION_TIME = 50
COLOR_SENSOR_GAIN = 4


# --------------------------------------------------------------------------
# IMU
# --------------------------------------------------------------------------
#
# The exact IMU has not been selected yet.
#
# Keep this abstraction so that we can later replace the placeholder with:
#
#     BNO055
#     BNO085
#     MPU6050
#     ICM20948
#     etc.
#
# without rewriting Navigation.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# DRUM
# --------------------------------------------------------------------------
#
# 28BYJ-48 + ULN2003
#
# GPIOs below connect to ULN2003 IN1-IN4.
#
# DO NOT connect the 28BYJ-48 coils directly to Raspberry Pi GPIO.
# --------------------------------------------------------------------------

DRUM_IN1_PIN = 21
DRUM_IN2_PIN = 2
DRUM_IN3_PIN = 3
DRUM_IN4_PIN = 15

DRUM_HOME_PIN = 1

DRUM_STEPS_PER_REV = 4096

DRUM_SLOTS = 4

DRUM_SLOT_ANGLE = 360.0 / DRUM_SLOTS

DRUM_HOME_TIMEOUT_SEC = 10.0

DRUM_STEP_DELAY_SEC = 0.002


# --------------------------------------------------------------------------
# DRUM SLOT DEFINITIONS
# --------------------------------------------------------------------------
#
# Physical layout:
#
#             RED
#              1
#
#       Y1  4     2  Y2
#
#            GREEN
#              3
#
# IMPORTANT:
# These numbers are LOGICAL slot numbers.
#
# The actual physical clockwise direction must be determined during
# calibration.
# --------------------------------------------------------------------------

SLOT_RED = 1
SLOT_YELLOW_PCC1 = 2
SLOT_GREEN = 3
SLOT_YELLOW_PCC2 = 4


# --------------------------------------------------------------------------
# PICKUP / TRAPDOOR SERVOS
# --------------------------------------------------------------------------

PICKUP_SERVO_PIN = 0
TRAPDOOR_SERVO_PIN = 29

# GPIO 29 is included here only as an example.
# Check your Pi board and gpiozero pin support before using it.
#
# Servo positions MUST be calibrated on the physical mechanism.

PICKUP_UP_POSITION = 0.75
PICKUP_DOWN_POSITION = -0.75

TRAPDOOR_CLOSED_POSITION = -0.80
TRAPDOOR_OPEN_POSITION = 0.80


# --------------------------------------------------------------------------
# EMERGENCY STOP
# --------------------------------------------------------------------------
#
# This is a SOFTWARE emergency-stop input.
#
# Ideally the actual E-stop should physically disconnect motor power.
# --------------------------------------------------------------------------

ESTOP_PIN = 28

# Assume:
#
#     released = HIGH
#     pressed  = LOW
#
# using an internal pull-up.
ESTOP_ACTIVE_LOW = True


# --------------------------------------------------------------------------
# MISSION LIMITS
# --------------------------------------------------------------------------

COMPETITION_TIME_LIMIT_SEC = 120.0

LINE_TIMEOUT_SEC = 8.0

LINE_DEBOUNCE_COUNT = 3

PATIENT_COUNT = 12

RED_PATIENT_COUNT = 4
YELLOW_PATIENT_COUNT = 4
GREEN_PATIENT_COUNT = 4


# ============================================================================
# GLOBAL SAFETY STATE
# ============================================================================

SAFETY_STOP = False

MISSION_START_TIME = None


# ============================================================================
# SAFETY CONTROLLER
# ============================================================================

class SafetyController:
    """
    Central safety system.

    Every movement operation should periodically call check().
    """

    def __init__(self):
        self.estop = Button(
            ESTOP_PIN,
            pull_up=True
        )

        self.estop.when_pressed = self.trigger_stop

        self.triggered = False

    def trigger_stop(self):
        global SAFETY_STOP

        SAFETY_STOP = True
        self.triggered = True

    def check(self):
        """
        Raise an exception if the robot should stop.
        """

        if SAFETY_STOP:
            raise RuntimeError(
                "SAFETY STOP ACTIVE"
            )

        if self.estop.is_pressed:
            raise RuntimeError(
                "EMERGENCY STOP PRESSED"
            )

        if MISSION_START_TIME is not None:

            elapsed = (
                time.monotonic()
                - MISSION_START_TIME
            )

            if elapsed > COMPETITION_TIME_LIMIT_SEC:
                raise RuntimeError(
                    "Competition time limit exceeded"
                )

    def reset(self):
        global SAFETY_STOP

        SAFETY_STOP = False
        self.triggered = False


# ============================================================================
# ENCODER
# ============================================================================

class Encoder:

    def __init__(self, pin):

        self.count = 0

        self.sensor = Button(
            pin,
            pull_up=True
        )

        self.sensor.when_pressed = (
            self.increment
        )

    def increment(self):
        self.count += 1

    def reset(self):
        self.count = 0

    def distance_mm(self):

        if ENCODER_COUNTS_PER_REV <= 0:
            return 0.0

        revolutions = (
            self.count /
            ENCODER_COUNTS_PER_REV
        )

        return (
            revolutions *
            WHEEL_CIRCUMFERENCE_MM
        )


# ============================================================================
# MOTOR
# ============================================================================

class Motor:

    def __init__(
        self,
        pwm_pin,
        direction_pin,
        encoder_pin,
        safety
    ):

        self.safety = safety

        self.pwm = PWMOutputDevice(
            pwm_pin,
            frequency=MOTOR_PWM_FREQUENCY_HZ,
            initial_value=0
        )

        self.direction = DigitalOutputDevice(
            direction_pin,
            initial_value=False
        )

        self.encoder = Encoder(
            encoder_pin
        )

    def set(self, speed):

        self.safety.check()

        speed = max(
            -MAX_MOTOR_SPEED,
            min(MAX_MOTOR_SPEED, speed)
        )

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


# ============================================================================
# DRIVE SYSTEM
# ============================================================================

class DriveSystem:

    def __init__(self, safety):

        self.left_front = Motor(
            LEFT_FRONT_PWM_PIN,
            LEFT_FRONT_DIR_PIN,
            LEFT_FRONT_ENCODER_PIN,
            safety
        )

        self.left_rear = Motor(
            LEFT_REAR_PWM_PIN,
            LEFT_REAR_DIR_PIN,
            LEFT_REAR_ENCODER_PIN,
            safety
        )

        self.right_front = Motor(
            RIGHT_FRONT_PWM_PIN,
            RIGHT_FRONT_DIR_PIN,
            RIGHT_FRONT_ENCODER_PIN,
            safety
        )

        self.right_rear = Motor(
            RIGHT_REAR_PWM_PIN,
            RIGHT_REAR_DIR_PIN,
            RIGHT_REAR_ENCODER_PIN,
            safety
        )

    def set_left(self, speed):

        self.left_front.set(speed)
        self.left_rear.set(speed)

    def set_right(self, speed):

        self.right_front.set(speed)
        self.right_rear.set(speed)

    def set(self, left, right):

        self.set_left(left)
        self.set_right(right)

    def forward(self, speed=DEFAULT_FORWARD_SPEED):

        self.set(speed, speed)

    def reverse(self, speed=DEFAULT_REVERSE_SPEED):

        self.set(-speed, -speed)

    def turn_left(self, speed=0.30):

        self.set(-speed, speed)

    def turn_right(self, speed=0.30):

        self.set(speed, -speed)

    def stop(self):

        self.left_front.stop()
        self.left_rear.stop()
        self.right_front.stop()
        self.right_rear.stop()

    def reset_encoders(self):

        self.left_front.reset_encoder()
        self.left_rear.reset_encoder()
        self.right_front.reset_encoder()
        self.right_rear.reset_encoder()

    def left_distance(self):

        return (
            self.left_front.distance_mm()
            +
            self.left_rear.distance_mm()
        ) / 2.0

    def right_distance(self):

        return (
            self.right_front.distance_mm()
            +
            self.right_rear.distance_mm()
        ) / 2.0

    def distance(self):

        return (
            self.left_distance()
            +
            self.right_distance()
        ) / 2.0


# ============================================================================
# IR SENSOR ARRAYS
# ============================================================================

class LineSensors:

    def __init__(self):

        self.left = [
            Button(
                pin,
                pull_up=True
            )
            for pin in LEFT_IR_PINS
        ]

        self.right = [
            Button(
                pin,
                pull_up=True
            )
            for pin in RIGHT_IR_PINS
        ]

    def left_values(self):

        return [
            sensor.is_pressed
            for sensor in self.left
        ]

    def right_values(self):

        return [
            sensor.is_pressed
            for sensor in self.right
        ]

    def all_high(self):

        values = (
            self.left_values()
            +
            self.right_values()
        )

        return (
            len(values) > 0
            and
            all(values)
        )

    def left_high(self):

        return all(
            self.left_values()
        )

    def right_high(self):

        return all(
            self.right_values()
        )

    def active_count_left(self):

        return sum(
            self.left_values()
        )

    def active_count_right(self):

        return sum(
            self.right_values()
        )


# ============================================================================
# TOF SENSORS
# ============================================================================

class ToFSensors:

    def __init__(self):

        self.i2c = busio.I2C(
            I2C_SCL,
            I2C_SDA
        )

        # XSHUT controls.
        self.front_shutdown = DigitalOutputDevice(
            TOF_FRONT_XSHUT_PIN,
            initial_value=False
        )

        self.side_shutdown = DigitalOutputDevice(
            TOF_SIDE_XSHUT_PIN,
            initial_value=False
        )

        self.front = None
        self.side = None

        self.setup()

    def setup(self):

        """
        Give each VL53L0X a unique address.

        Both sensors initially use the same default address.
        """

        # Keep both disabled.
        self.front_shutdown.off()
        self.side_shutdown.off()

        time.sleep(0.1)

        # Enable front sensor.
        self.front_shutdown.on()
        time.sleep(0.1)

        self.front = adafruit_vl53l0x.VL53L0X(
            self.i2c
        )

        self.front.set_address(
            TOF_FRONT_ADDRESS
        )

        # Enable side sensor.
        self.side_shutdown.on()
        time.sleep(0.1)

        self.side = adafruit_vl53l0x.VL53L0X(
            self.i2c
        )

        self.side.set_address(
            TOF_SIDE_ADDRESS
        )

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

    def front_contact(self):

        distance = self.front_mm()

        # Sensor failure must NOT be treated as "wall detected"
        # during normal operation.
        if distance is None:
            return False

        return (
            distance <= WALL_STOP_DISTANCE_MM
        )

    def side_contact(self):

        distance = self.side_mm()

        if distance is None:
            return False

        return (
            distance <= WALL_STOP_DISTANCE_MM
        )


# ============================================================================
# COLOR SENSOR
# ============================================================================

class ColorSensor:

    def __init__(self):

        self.i2c = busio.I2C(
            I2C_SCL,
            I2C_SDA
        )

        self.sensor = (
            adafruit_tcs34725.TCS34725(
                self.i2c
            )
        )

        self.sensor.integration_time = (
            COLOR_SENSOR_INTEGRATION_TIME
        )

        self.sensor.gain = (
            COLOR_SENSOR_GAIN
        )

    def read(self):

        red = 0
        green = 0
        blue = 0

        for _ in range(COLOR_SAMPLES):

            r, g, b, _ = (
                self.sensor.color_raw()
            )

            red += r
            green += g
            blue += b

            time.sleep(
                COLOR_SAMPLE_DELAY_SEC
            )

        red /= COLOR_SAMPLES
        green /= COLOR_SAMPLES
        blue /= COLOR_SAMPLES

        total = (
            red +
            green +
            blue
        )

        if total <= 0:
            return None

        r = red / total
        g = green / total
        b = blue / total

        # THESE THRESHOLDS MUST BE CALIBRATED
        # WITH THE ACTUAL PATIENT COLORS AND LIGHTING.

        if (
            r > 0.42
            and r > g * 1.25
            and r > b * 1.35
        ):
            return "red"

        if (
            r > 0.30
            and g > 0.30
            and b < 0.20
        ):
            return "yellow"

        if (
            g > 0.40
            and g > r * 1.15
            and g > b * 1.20
        ):
            return "green"

        return None


# ============================================================================
# DRUM
# ============================================================================

class Drum:

    # Half-step sequence for the 28BYJ-48.
    STEP_SEQUENCE = [
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 1, 1, 0],
        [0, 0, 1, 0],
        [0, 0, 1, 1],
        [0, 0, 0, 1],
        [1, 0, 0, 1]
    ]

    def __init__(self, safety):

        self.safety = safety

        self.coils = [
            DigitalOutputDevice(
                DRUM_IN1_PIN
            ),
            DigitalOutputDevice(
                DRUM_IN2_PIN
            ),
            DigitalOutputDevice(
                DRUM_IN3_PIN
            ),
            DigitalOutputDevice(
                DRUM_IN4_PIN
            )
        ]

        self.home = Button(
            DRUM_HOME_PIN,
            pull_up=True
        )

        self.current_slot = 1
        self.current_step = 0

    def release(self):

        for coil in self.coils:
            coil.off()

    def apply_step(self, step):

        for i in range(4):

            if step[i]:
                self.coils[i].on()
            else:
                self.coils[i].off()

    def single_step(self, direction):

        self.safety.check()

        self.current_step += direction

        self.current_step %= len(
            self.STEP_SEQUENCE
        )

        self.apply_step(
            self.STEP_SEQUENCE[
                self.current_step
            ]
        )

        time.sleep(
            DRUM_STEP_DELAY_SEC
        )

    def home_drum(self):

        """
        Move toward the physical home switch.

        The home switch establishes slot 1.
        """

        start = time.monotonic()

        # The direction here is an assumption.
        # Reverse this if your mechanical drum homes in the other direction.
        while not self.home.is_pressed:

            self.safety.check()

            if (
                time.monotonic() - start
                >
                DRUM_HOME_TIMEOUT_SEC
            ):
                self.release()

                raise RuntimeError(
                    "Drum homing timeout"
                )

            self.single_step(-1)

        self.release()

        self.current_slot = 1

        self.current_step = 0

    def rotate_to(self, target_slot):

        if target_slot not in (
            SLOT_RED,
            SLOT_YELLOW_PCC1,
            SLOT_GREEN,
            SLOT_YELLOW_PCC2
        ):
            raise ValueError(
                "Invalid drum slot"
            )

        current = self.current_slot

        # Logical four-position shortest path.
        delta = (
            target_slot -
            current
        ) % 4

        if delta == 0:
            return

        # For now we only use the positive direction.
        #
        # Later this can be replaced by a calibrated shortest-path
        # implementation once the actual physical clockwise direction
        # is confirmed.
        steps_per_slot = (
            DRUM_STEPS_PER_REV // 4
        )

        steps = delta * steps_per_slot

        for _ in range(steps):

            self.safety.check()

            self.single_step(1)

        self.release()

        self.current_slot = target_slot


# ============================================================================
# IMU ABSTRACTION
# ============================================================================

class IMU:

    """
    Placeholder until the exact IMU is selected.

    DO NOT pretend heading is available when the physical IMU isn't
    installed.

    Navigation can still operate using encoders and line landmarks.
    """

    def __init__(self):

        self.heading = 0.0

    def available(self):

        return False

    def read_heading(self):

        return self.heading

    def reset_heading(self):

        self.heading = 0.0


# ============================================================================
# NAVIGATION
# ============================================================================

class Navigation:

    def __init__(
        self,
        drive,
        lines,
        tof,
        imu,
        safety
    ):

        self.drive = drive
        self.lines = lines
        self.tof = tof
        self.imu = imu
        self.safety = safety

    def reset_checkpoint(self):

        self.drive.reset_encoders()

    def line_checkpoint(self):

        """
        Wait until all line sensors detect the landmark.

        A debounce counter prevents one noisy reading from triggering
        a major route transition.
        """

        start = time.monotonic()
        high_count = 0

        while (
            time.monotonic() - start
            <
            LINE_TIMEOUT_SEC
        ):

            self.safety.check()

            if self.lines.all_high():

                high_count += 1

                if (
                    high_count
                    >= LINE_DEBOUNCE_COUNT
                ):
                    self.drive.stop()

                    self.reset_checkpoint()

                    return

            else:

                high_count = 0

            self.drive.forward(
                DEFAULT_FORWARD_SPEED
            )

            time.sleep(0.005)

        self.drive.stop()

        raise RuntimeError(
            "IR line checkpoint timeout"
        )

    def wall_checkpoint(self):

        start = time.monotonic()

        while (
            time.monotonic() - start
            <
            TOF_TIMEOUT_SEC
        ):

            self.safety.check()

            distance = (
                self.tof.front_mm()
            )

            if distance is not None:

                if (
                    distance
                    <=
                    WALL_STOP_DISTANCE_MM
                ):

                    self.drive.stop()

                    self.reset_checkpoint()

                    return

            self.drive.forward(
                0.25
            )

            time.sleep(0.01)

        self.drive.stop()

        raise RuntimeError(
            "ToF checkpoint timeout"
        )

    def drive_distance(
        self,
        distance_mm,
        speed=DEFAULT_FORWARD_SPEED
    ):

        self.drive.reset_encoders()

        start = time.monotonic()

        while (
            self.drive.distance()
            <
            distance_mm
        ):

            self.safety.check()

            if (
                time.monotonic() - start
                >
                MAX_MOVEMENT_TIME_SEC
            ):

                self.drive.stop()

                raise RuntimeError(
                    "Drive-distance timeout"
                )

            left = (
                self.drive.left_distance()
            )

            right = (
                self.drive.right_distance()
            )

            # Basic encoder synchronization.
            error = left - right

            correction = (
                error * 0.01
            )

            left_speed = (
                speed - correction
            )

            right_speed = (
                speed + correction
            )

            self.drive.set(
                left_speed,
                right_speed
            )

            time.sleep(0.005)

        self.drive.stop()

    def turn_to(self, target):

        """
        Use IMU if available.

        Until the actual IMU is installed, this function stops safely
        rather than pretending that a heading exists.
        """

        if not self.imu.available():

            self.drive.stop()

            raise RuntimeError(
                "IMU heading requested, "
                "but no IMU is configured"
            )

        start = time.monotonic()

        while True:

            self.safety.check()

            if (
                time.monotonic() - start
                >
                MAX_MOVEMENT_TIME_SEC
            ):

                self.drive.stop()

                raise RuntimeError(
                    "Turn timeout"
                )

            current = (
                self.imu.read_heading()
            )

            error = (
                target -
                current +
                180
            ) % 360 - 180

            if abs(error) <= 2.0:

                break

            speed = min(
                0.45,
                max(
                    0.18,
                    abs(error) * 0.01
                )
            )

            if error > 0:

                self.drive.turn_right(
                    speed
                )

            else:

                self.drive.turn_left(
                    speed
                )

            time.sleep(0.01)

        self.drive.stop()


# ============================================================================
# PATIENT ROBOT
# ============================================================================

class PatientRobot:

    def __init__(self):

        global MISSION_START_TIME

        self.safety = SafetyController()

        self.drive = DriveSystem(
            self.safety
        )

        self.lines = LineSensors()

        self.tof = ToFSensors()

        self.color = ColorSensor()

        self.drum = Drum(
            self.safety
        )

        self.imu = IMU()

        self.navigation = Navigation(
            self.drive,
            self.lines,
            self.tof,
            self.imu,
            self.safety
        )

        # Mission state.
        self.patient_count = 0

        self.red_count = 0
        self.yellow_count = 0
        self.green_count = 0

        # Yellow patients are assigned alternately.
        self.yellow_toggle = 0

        MISSION_START_TIME = None

    def slot_for_color(self, color):

        if color == "red":

            self.red_count += 1

            return SLOT_RED

        if color == "green":

            self.green_count += 1

            return SLOT_GREEN

        if color == "yellow":

            self.yellow_count += 1

            if self.yellow_toggle == 0:

                self.yellow_toggle = 1

                return SLOT_YELLOW_PCC1

            else:

                self.yellow_toggle = 0

                return SLOT_YELLOW_PCC2

        return None

    def identify_patient(self):

        """
        Try multiple color readings.

        A failed color reading is a mission error rather than silently
        guessing the patient's destination.
        """

        for _ in range(
            COLOR_RETRY_COUNT
        ):

            self.safety.check()

            color = (
                self.color.read()
            )

            if color is not None:

                return color

            time.sleep(0.05)

        raise RuntimeError(
            "Unable to identify patient color"
        )

    def collect_patient(self):

        """
        Placeholder for the actual pickup mechanism.

        IMPORTANT:
        This is where the servo-powered ramp/lift will eventually be
        controlled.

        The actual mechanism needs to be tested before autonomous
        operation.
        """

        self.safety.check()

        print("Pickup mechanism: DOWN")

        # TODO:
        # pickup_servo.value = PICKUP_DOWN_POSITION

        time.sleep(0.20)

        print("Pickup mechanism: UP")

        # TODO:
        # pickup_servo.value = PICKUP_UP_POSITION

        time.sleep(0.20)

        color = (
            self.identify_patient()
        )

        slot = (
            self.slot_for_color(color)
        )

        if slot is None:

            raise RuntimeError(
                "Invalid patient color"
            )

        print(
            f"Patient {self.patient_count + 1}: "
            f"{color} -> drum slot {slot}"
        )

        # Rotate drum immediately after identification.
        #
        # In the final version this should be scheduled alongside
        # navigation so the robot doesn't unnecessarily stop.
        self.drum.rotate_to(slot)

        self.patient_count += 1

    def dispense(self, slot):

        """
        Open the trapdoor at the appropriate drum position.

        The actual servo positions need physical calibration.
        """

        self.safety.check()

        self.drum.rotate_to(slot)

        print(
            f"Dispensing drum slot {slot}"
        )

        # TODO:
        # trapdoor_servo.value = TRAPDOOR_OPEN_POSITION

        time.sleep(0.5)

        # TODO:
        # trapdoor_servo.value = TRAPDOOR_CLOSED_POSITION

        time.sleep(0.3)

    def collect_all_patients(self):

        """
        TEMPORARY TEST ROUTE.

        These distances are placeholders.

        DO NOT run this on the competition board until every distance,
        turn and sensor landmark has been calibrated.
        """

        for _ in range(PATIENT_COUNT):

            self.safety.check()

            # TODO:
            # Replace with the actual patient approach routine.
            self.navigation.drive_distance(
                200
            )

            self.collect_patient()

    def run(self):

        global MISSION_START_TIME

        try:

            print()
            print("==============================")
            print("CR8S STARTING")
            print(
                f"Software: "
                f"{CR8S_SOFTWARE_VERSION}"
            )
            print("==============================")

            # Establish a known drum position.
            print("Homing drum...")

            self.drum.home_drum()

            print("Drum homed.")

            # The competition timer should start when the robot actually
            # begins its mission.
            MISSION_START_TIME = (
                time.monotonic()
            )

            # ----------------------------------------------------------
            # START ZONE
            # ----------------------------------------------------------

            print(
                "Leaving starting zone..."
            )

            self.navigation.line_checkpoint()

            # ----------------------------------------------------------
            # PATIENT LOOP
            # ----------------------------------------------------------

            print(
                "Entering patient loop..."
            )

            self.collect_all_patients()

            # ----------------------------------------------------------
            # PCC1
            # ----------------------------------------------------------

            print("Going to PCC1...")

            # TODO:
            # Replace with calibrated route.

            self.navigation.wall_checkpoint()

            self.dispense(
                SLOT_YELLOW_PCC1
            )

            # ----------------------------------------------------------
            # HOSPITAL
            # ----------------------------------------------------------

            print(
                "Going to Hospital..."
            )

            # TODO:
            # Replace with calibrated route.

            self.navigation.wall_checkpoint()

            self.dispense(
                SLOT_RED
            )

            # ----------------------------------------------------------
            # PCC2
            # ----------------------------------------------------------

            print(
                "Going to PCC2..."
            )

            # TODO:
            # Replace with calibrated route.

            self.navigation.wall_checkpoint()

            self.dispense(
                SLOT_YELLOW_PCC2
            )

            # ----------------------------------------------------------
            # START / GREEN
            # ----------------------------------------------------------

            print(
                "Returning to start..."
            )

            # TODO:
            # Replace with calibrated route.

            self.navigation.line_checkpoint()

            self.dispense(
                SLOT_GREEN
            )

            print()
            print("==============================")
            print("MISSION COMPLETE")
            print("==============================")

        except Exception as error:

            print()
            print("==============================")
            print("CR8S EMERGENCY STOP")
            print("==============================")
            print(
                f"Reason: {error}"
            )

            raise

        finally:

            # THIS MUST ALWAYS HAPPEN.
            #
            # Even if a sensor throws an exception,
            # motors are turned off.
            self.drive.stop()

            self.drum.release()

            print(
                "All motion outputs disabled."
            )


# ============================================================================
# STARTUP
# ============================================================================

def main():

    robot = None

    try:

        robot = PatientRobot()

        robot.run()

    except KeyboardInterrupt:

        print(
            "\nKeyboard interrupt."
        )

    except Exception as error:

        print(
            f"\nFatal error: {error}"
        )

    finally:

        if robot is not None:

            robot.drive.stop()

            robot.drum.release()

        print(
            "CR8S safely stopped."
        )


if __name__ == "__main__":

    main()

