"""
crates.py  |  CR8S  |  TearX ST59
Robot 1: patient collection, colour sorting, medkit delivery.

DO NOT RUN ON HARDWARE until every value marked TODO:MEASURE or
TODO:WIRE has been filled in and verified with a multimeter / test run.

Robot 2 (galileo.py) handles samples, lab, and containment beams.
This file intentionally contains nothing for Robot 2.

--------------------------------------------------------------------
KNOWN CONFLICTS / OPEN ITEMS  (resolve before competition)
--------------------------------------------------------------------
CONFLICT 1 — RAMP SERVO vs MOTOR PWM:
  The wiring plan assigns GPIO 12 to left-front motor PWMA.
  The Pi's only hardware PWM pins are 12 and 13 (and their alt
  pairs 18/19 which are also taken by right-side motors).
  Software PWM on any other pin will cause servo jitter under load.
  OPTIONS:
    a) Use a PCA9685/servo HAT just for the ramp servo.
    b) Remap one motor channel to free up GPIO 12 or 13.
    c) Accept software PWM jitter on the ramp servo (low risk since
       the ramp only moves twice per patient and doesn't hold load).
  Currently using RAMP_SERVO_PIN = None  →  set before running.

CONFLICT 2 — GPIO PIN COUNT:
  With full quadrature encoding (A+B per wheel = 8 pins) +
  8 IR inputs + motor control, there are not enough Pi GPIO pins.
  Current plan: use ENCODER_B pins only if you free up IR pins,
  otherwise leave ENCODER_B_PIN = None for single-edge counting
  (halves resolution, still works for distance estimation).
  IR is currently on direct GPIO (no MCP23017 per latest spec).

CONFLICT 3 — NO E-STOP:
  The rulebook requires a physically accessible emergency stop.
  Without one you risk disqualification before the match starts.
  Minimum fix: a rocker switch in the battery power line.
  Software only is not sufficient.

CONFLICT 4 — NO TEST RUNS OR MEASURED DISTANCES:
  All route distances are macros set to 0. The robot will not move
  meaningful distances until these are measured and filled in.
  Measure on the real field surface — carpet vs hard floor changes
  effective wheel diameter significantly.

CONFLICT 5 — DRUM STEPPER DRIVER:
  Using a TB6612FNG in 4-phase mode for the 28BYJ-48.
  TB6612 AIN1/AIN2/BIN1/BIN2 → stepper IN1/IN2/IN3/IN4.
  The TB6612 STBY pin must be held HIGH for the stepper to move.
  Coil sequence below assumes standard 28BYJ-48 half-step order.
  Verify against your specific motor — a wrong sequence stalls it.
--------------------------------------------------------------------
"""

import math
import time

import board
import busio
import adafruit_tcs34725
import adafruit_vl53l0x
from gpiozero import (
    Button,
    DigitalOutputDevice,
    PWMOutputDevice,
    Servo,
)


# ====================================================================
# SECTION 1: CONFIGURATION MACROS
# Fill in every value marked TODO before running on hardware.
# ====================================================================

# --- Wheel geometry -------------------------------------------------
WHEEL_DIAMETER_MM        = 42.0          # TODO:MEASURE with calipers
ENCODER_CPR              = 0             # TODO:MEASURE counts/rev for
                                         # your specific N20 variant.
                                         # Common: 7 or 11 PPR * gear
                                         # ratio printed on the motor.
                                         # Count pulses for one full
                                         # wheel turn to confirm.

# --- Motor timing ---------------------------------------------------
MOTOR_PWM_HZ             = 1000
FORWARD_SPEED            = 0.40          # TODO:TUNE 0.0-1.0
REVERSE_SPEED            = 0.35          # TODO:TUNE
TURN_SPEED               = 0.30          # TODO:TUNE
MAX_SPEED                = 0.70

# --- TB6612FNG #1 (left motors) ------------------------------------
LF_PWM_PIN               = 12           # Left-front PWMA
LF_IN1_PIN               = 5            # Left-front AIN1
LF_IN2_PIN               = 6            # Left-front AIN2
LR_PWM_PIN               = 13           # Left-rear PWMB
LR_IN1_PIN               = 16           # Left-rear BIN1
LR_IN2_PIN               = 20           # Left-rear BIN2
TB1_STBY_PIN             = 21           # TB6612 #1 standby

# --- TB6612FNG #2 (right motors) -----------------------------------
RF_PWM_PIN               = 18           # Right-front PWMA
RF_IN1_PIN               = 23           # Right-front AIN1
RF_IN2_PIN               = 24           # Right-front AIN2
RR_PWM_PIN               = 19           # Right-rear PWMB
RR_IN1_PIN               = 25           # Right-rear BIN1
RR_IN2_PIN               = 26           # Right-rear BIN2
TB2_STBY_PIN             = 27           # TB6612 #2 standby

# --- Encoders -------------------------------------------------------
LF_ENC_A_PIN             = 4
LF_ENC_B_PIN             = 7            # Set None if pin not wired
LR_ENC_A_PIN             = 8
LR_ENC_B_PIN             = 9            # Set None if pin not wired
RF_ENC_A_PIN             = 10
RF_ENC_B_PIN             = 11           # Set None if pin not wired
RR_ENC_A_PIN             = 14
RR_ENC_B_PIN             = 15           # Set None if pin not wired

# --- IR arrays (direct GPIO, active-low: black=LOW) ----------------
# 4 sensors per side. Adjust pin list if your RLS08 has a different
# output count.
LEFT_IR_PINS             = []           # TODO:WIRE e.g. [29,31,33,35]
RIGHT_IR_PINS            = []           # TODO:WIRE

# --- ToF sensors ----------------------------------------------------
TOF_FRONT_XSHUT_PIN      = 17
TOF_SIDE_XSHUT_PIN       = 22
TOF_FRONT_I2C_ADDR       = 0x30
TOF_SIDE_I2C_ADDR        = 0x31
WALL_STOP_MM             = 30           # TODO:TUNE stop distance

# --- Ramp servo -----------------------------------------------------
# See CONFLICT 1 above before wiring this.
RAMP_SERVO_PIN           = None         # TODO:WIRE (needs hw PWM pin)
RAMP_SERVO_CLOSED        = -1.0         # TODO:TUNE gpiozero -1..+1
RAMP_SERVO_OPEN          = 1.0          # TODO:TUNE
RAMP_MOVE_TIME_SEC       = 0.4          # TODO:TUNE

# --- Drum stepper (28BYJ-48 via dedicated TB6612FNG) ---------------
# Wire TB6612 AIN1/AIN2/BIN1/BIN2 to stepper IN1/IN2/IN3/IN4.
DRUM_IN1_PIN             = None         # TODO:WIRE stepper IN1
DRUM_IN2_PIN             = None         # TODO:WIRE stepper IN2
DRUM_IN3_PIN             = None         # TODO:WIRE stepper IN3
DRUM_IN4_PIN             = None         # TODO:WIRE stepper IN4
DRUM_STBY_PIN            = None         # TODO:WIRE TB6612 STBY for drum
DRUM_STEPS_PER_REV       = 4096         # 28BYJ-48 half-step = 4096
DRUM_STEPS_PER_SLOT      = DRUM_STEPS_PER_REV // 4   # 1024
DRUM_STEP_DELAY_SEC      = 0.001        # TODO:TUNE (too fast = stall)

# --- Slot assignments -----------------------------------------------
# Physical drum layout (looking from above, manual start = slot 1):
#   1  2
#   4  3
# Rotation: delta = (target - current) % 4 clockwise steps
SLOT_RED                 = 1    # Hospital: 4 patients, 6 kits
SLOT_YELLOW_PCC1         = 2    # PCC1: 2 patients, 2 kits
SLOT_YELLOW_PCC2         = 3    # PCC2: 2 patients, 2 kits  
SLOT_GREEN               = 4    # Recovery zone: 4 patients, 0 kits

# --- Colour sensor --------------------------------------------------
COLOR_SAMPLES            = 5
COLOR_SAMPLE_DELAY       = 0.02
COLOR_RETRIES            = 5
COLOR_INTEGRATION_TIME   = 50
COLOR_GAIN               = 4
# Thresholds: calibrate under competition lighting with real cylinders
COLOR_RED_R_MIN          = 0.42
COLOR_RED_R_VS_G         = 1.25
COLOR_RED_R_VS_B         = 1.35
COLOR_YELLOW_R_MIN       = 0.30
COLOR_YELLOW_G_MIN       = 0.30
COLOR_YELLOW_B_MAX       = 0.20
COLOR_GREEN_G_MIN        = 0.40
COLOR_GREEN_G_VS_R       = 1.15
COLOR_GREEN_G_VS_B       = 1.20

# --- Timeouts -------------------------------------------------------
LINE_TIMEOUT_SEC         = 8.0
TOF_TIMEOUT_SEC          = 5.0
MOVE_TIMEOUT_SEC         = 10.0
LINE_DEBOUNCE            = 3           # consecutive all-high reads
LINE_RETRIES             = 3
WALL_RETRIES             = 3
COMPETITION_TIME_SEC     = 115.0       # 5s margin under 120s limit

# --- Route distances (ALL ZERO until measured on real field) --------
# The U-path visits all 12 patient positions.
# Measure distance in mm from each stop to the next.
# Must have exactly 12 entries.
PATIENT_ROUTE_MM         = [0] * 12   # TODO:MEASURE all 12 legs

# Turn durations for 90-degree pivot (encoder-only, no IMU).
# Tune by commanding a turn and adjusting until heading is 90 deg.
TURN_90_SEC              = 0.0         # TODO:TUNE
TURN_180_SEC             = 0.0         # TODO:TUNE

# Delivery distances
DIST_TO_PCC1_MM          = 0           # TODO:MEASURE
DIST_TO_HOSPITAL_MM      = 0           # TODO:MEASURE
DIST_TO_PCC2_MM          = 0           # TODO:MEASURE
DIST_TO_RZ_MM            = 0           # TODO:MEASURE
DIST_BACK_FROM_PCC1_MM   = 0           # TODO:MEASURE reverse leg
DIST_BACK_FROM_HOSP_MM   = 0           # TODO:MEASURE reverse leg
DIST_BACK_FROM_PCC2_MM   = 0           # TODO:MEASURE reverse leg


# ====================================================================
# SECTION 2: HARDWARE VALIDATION
# ====================================================================

def require_configuration():
    """Crash loudly before touching motors if critical pins are None."""
    motor_pins = [
        LF_PWM_PIN, LF_IN1_PIN, LF_IN2_PIN,
        LR_PWM_PIN, LR_IN1_PIN, LR_IN2_PIN,
        RF_PWM_PIN, RF_IN1_PIN, RF_IN2_PIN,
        RR_PWM_PIN, RR_IN1_PIN, RR_IN2_PIN,
        TB1_STBY_PIN, TB2_STBY_PIN,
    ]
    if any(p is None for p in motor_pins):
        raise RuntimeError("Motor GPIO pins are not fully configured")

    if ENCODER_CPR <= 0:
        raise RuntimeError(
            "ENCODER_CPR must be measured and set before running. "
            "Count pulses for one full wheel revolution."
        )

    if not LEFT_IR_PINS or not RIGHT_IR_PINS:
        raise RuntimeError("IR sensor GPIO pin lists are empty")

    drum_pins = [DRUM_IN1_PIN, DRUM_IN2_PIN, DRUM_IN3_PIN,
                 DRUM_IN4_PIN, DRUM_STBY_PIN]
    if any(p is None for p in drum_pins):
        raise RuntimeError("Drum stepper GPIO pins are not configured")

    if RAMP_SERVO_PIN is None:
        raise RuntimeError(
            "RAMP_SERVO_PIN is not set. Resolve CONFLICT 1 first."
        )

    if len(PATIENT_ROUTE_MM) != 12:
        raise RuntimeError("PATIENT_ROUTE_MM must have exactly 12 entries")


# ====================================================================
# SECTION 3: ENCODERS
# ====================================================================

class Encoder:
    """
    Single-edge counter on pin A. If pin B is wired, it is registered
    but direction decoding is not implemented yet — add it once the
    encoder wiring is verified to be 3.3V-safe.
    """

    def __init__(self, pin_a, pin_b=None):
        self._count = 0
        self._sensor_a = Button(pin_a, pull_up=True)
        self._sensor_a.when_pressed = self._tick
        if pin_b is not None:
            # Retained as placeholder; wired but not decoded yet.
            self._sensor_b = Button(pin_b, pull_up=True)

    def _tick(self):
        self._count += 1

    def reset(self):
        self._count = 0

    @property
    def count(self):
        return self._count

    def distance_mm(self):
        if ENCODER_CPR <= 0:
            return 0.0
        circumference = math.pi * WHEEL_DIAMETER_MM
        return (self._count / ENCODER_CPR) * circumference


# ====================================================================
# SECTION 4: MOTORS (TB6612FNG — PWM + IN1 + IN2 + STBY)
# ====================================================================

class TB6612Motor:
    """
    One channel of a TB6612FNG.
    Forward:  IN1=H, IN2=L, PWM=speed
    Reverse:  IN1=L, IN2=H, PWM=speed
    Brake:    IN1=H, IN2=H (or both L)
    Standby is controlled at the driver level, not per-motor.
    """

    def __init__(self, pwm_pin, in1_pin, in2_pin, enc_a_pin, enc_b_pin=None):
        self.pwm = PWMOutputDevice(pwm_pin, frequency=MOTOR_PWM_HZ,
                                   initial_value=0)
        self.in1 = DigitalOutputDevice(in1_pin, initial_value=False)
        self.in2 = DigitalOutputDevice(in2_pin, initial_value=False)
        self.encoder = Encoder(enc_a_pin, enc_b_pin)

    def set(self, speed):
        """speed: -MAX_SPEED to +MAX_SPEED. Positive = forward."""
        speed = max(-MAX_SPEED, min(MAX_SPEED, float(speed)))
        if speed > 0:
            self.in1.on()
            self.in2.off()
            self.pwm.value = speed
        elif speed < 0:
            self.in1.off()
            self.in2.on()
            self.pwm.value = abs(speed)
        else:
            self.brake()

    def brake(self):
        self.in1.on()
        self.in2.on()
        self.pwm.value = 0

    def stop(self):
        self.in1.off()
        self.in2.off()
        self.pwm.value = 0

    def distance_mm(self):
        return self.encoder.distance_mm()

    def reset_encoder(self):
        self.encoder.reset()


class DriveSystem:
    """
    Four-wheel differential drive.
    Left side: lf (front) + lr (rear)
    Right side: rf (front) + rr (rear)
    Both TB6612 STBY pins must be HIGH to move.
    """

    def __init__(self):
        self.stby1 = DigitalOutputDevice(TB1_STBY_PIN, initial_value=False)
        self.stby2 = DigitalOutputDevice(TB2_STBY_PIN, initial_value=False)

        self.lf = TB6612Motor(LF_PWM_PIN, LF_IN1_PIN, LF_IN2_PIN,
                              LF_ENC_A_PIN, LF_ENC_B_PIN)
        self.lr = TB6612Motor(LR_PWM_PIN, LR_IN1_PIN, LR_IN2_PIN,
                              LR_ENC_A_PIN, LR_ENC_B_PIN)
        self.rf = TB6612Motor(RF_PWM_PIN, RF_IN1_PIN, RF_IN2_PIN,
                              RF_ENC_A_PIN, RF_ENC_B_PIN)
        self.rr = TB6612Motor(RR_PWM_PIN, RR_IN1_PIN, RR_IN2_PIN,
                              RR_ENC_A_PIN, RR_ENC_B_PIN)

    def enable(self):
        self.stby1.on()
        self.stby2.on()

    def disable(self):
        self.stby1.off()
        self.stby2.off()

    def _set(self, left, right):
        self.lf.set(left)
        self.lr.set(left)
        self.rf.set(right)
        self.rr.set(right)

    def forward(self, speed=None):
        self._set(speed or FORWARD_SPEED, speed or FORWARD_SPEED)

    def reverse(self, speed=None):
        s = speed or REVERSE_SPEED
        self._set(-s, -s)

    def turn_right(self, speed=None):
        # Left wheels forward, right wheels backward = clockwise turn
        s = speed or TURN_SPEED
        self._set(s, -s)

    def turn_left(self, speed=None):
        s = speed or TURN_SPEED
        self._set(-s, s)

    def stop(self):
        self.lf.stop()
        self.lr.stop()
        self.rf.stop()
        self.rr.stop()

    def reset_encoders(self):
        for m in (self.lf, self.lr, self.rf, self.rr):
            m.reset_encoder()

    def left_distance_mm(self):
        return (self.lf.distance_mm() + self.lr.distance_mm()) / 2.0

    def right_distance_mm(self):
        return (self.rf.distance_mm() + self.rr.distance_mm()) / 2.0

    def distance_mm(self):
        return (self.left_distance_mm() + self.right_distance_mm()) / 2.0


# ====================================================================
# SECTION 5: LINE SENSORS (active-low: black = LOW = is_pressed=True)
# ====================================================================

class LineSensors:
    """
    RLS08 arrays via direct GPIO.
    Black line → pin goes LOW → Button.is_pressed = True (pull_up=True)
    So: is_pressed == True means BLACK/ON-LINE.
    all_high() returns True when ALL sensors see black (line crossing).
    """

    def __init__(self):
        self.left  = [Button(p, pull_up=True) for p in LEFT_IR_PINS]
        self.right = [Button(p, pull_up=True) for p in RIGHT_IR_PINS]

    def left_on_line(self):
        return [s.is_pressed for s in self.left]

    def right_on_line(self):
        return [s.is_pressed for s in self.right]

    def all_high(self):
        """True when every sensor detects black (full tape crossing)."""
        all_sensors = self.left_on_line() + self.right_on_line()
        return bool(all_sensors) and all(all_sensors)

    def any_left(self):
        return any(self.left_on_line())

    def any_right(self):
        return any(self.right_on_line())


# ====================================================================
# SECTION 6: TOF SENSORS
# ====================================================================

class ToFSensors:
    """
    Two VL53L0X sensors sharing I2C.
    XSHUT sequence assigns unique addresses at startup.
    """

    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self._xshut_front = DigitalOutputDevice(TOF_FRONT_XSHUT_PIN,
                                                initial_value=False)
        self._xshut_side  = DigitalOutputDevice(TOF_SIDE_XSHUT_PIN,
                                                initial_value=False)
        self.front = None
        self.side  = None
        self._init_sensors()

    def _init_sensors(self):
        # Hold both in reset
        self._xshut_front.off()
        self._xshut_side.off()
        time.sleep(0.05)

        # Bring up front, assign address
        self._xshut_front.on()
        time.sleep(0.05)
        self.front = adafruit_vl53l0x.VL53L0X(self.i2c)
        self.front.set_address(TOF_FRONT_I2C_ADDR)

        # Bring up side, assign address
        self._xshut_side.on()
        time.sleep(0.05)
        self.side = adafruit_vl53l0x.VL53L0X(self.i2c)
        self.side.set_address(TOF_SIDE_I2C_ADDR)

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

    def front_near_wall(self):
        d = self.front_mm()
        # Treat None (sensor error) and <=0 (out of range) as contact
        if d is None or d <= 0:
            return True
        return d <= WALL_STOP_MM

    def side_near_wall(self):
        d = self.side_mm()
        if d is None or d <= 0:
            return True
        return d <= WALL_STOP_MM


# ====================================================================
# SECTION 7: COLOUR SENSOR (TCS34725)
# ====================================================================

class ColorSensor:
    """
    Averages COLOR_SAMPLES readings, normalises to RGB ratios,
    classifies. Thresholds are starting points — calibrate under
    competition lighting with the actual painted wooden cylinders.
    """

    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self._sensor = adafruit_tcs34725.TCS34725(i2c)
        self._sensor.integration_time = COLOR_INTEGRATION_TIME
        self._sensor.gain = COLOR_GAIN

    def read(self):
        """Returns 'red', 'yellow', 'green', or None."""
        r_sum = g_sum = b_sum = 0.0
        for _ in range(COLOR_SAMPLES):
            r, g, b, _ = self._sensor.color_raw()
            r_sum += r
            g_sum += g
            b_sum += b
            time.sleep(COLOR_SAMPLE_DELAY)

        total = r_sum + g_sum + b_sum
        if total <= 0:
            return None

        r = r_sum / total
        g = g_sum / total
        b = b_sum / total

        if (r > COLOR_RED_R_MIN
                and r > g * COLOR_RED_R_VS_G
                and r > b * COLOR_RED_R_VS_B):
            return "red"

        if (r > COLOR_YELLOW_R_MIN
                and g > COLOR_YELLOW_G_MIN
                and b < COLOR_YELLOW_B_MAX):
            return "yellow"

        if (g > COLOR_GREEN_G_MIN
                and g > r * COLOR_GREEN_G_VS_R
                and g > b * COLOR_GREEN_G_VS_B):
            return "green"

        return None


# ====================================================================
# SECTION 8: DRUM (28BYJ-48 via TB6612FNG in 4-phase mode)
# ====================================================================

class Drum:
    """
    28BYJ-48 driven through a dedicated TB6612FNG.
    TB6612 wiring: AIN1→IN1, AIN2→IN2, BIN1→IN3, BIN2→IN4.
    Half-step sequence: 8 steps per electrical cycle.
    Drum has 4 compartments; one slot = DRUM_STEPS_PER_SLOT steps.
    No home switch — drum must be manually pre-aligned to slot 1
    (red/hospital position) before the match starts.
    """

    # Half-step sequence for 28BYJ-48
    # (IN1, IN2, IN3, IN4)
    HALF_STEP = [
        (1, 0, 0, 0),
        (1, 1, 0, 0),
        (0, 1, 0, 0),
        (0, 1, 1, 0),
        (0, 0, 1, 0),
        (0, 0, 1, 1),
        (0, 0, 0, 1),
        (1, 0, 0, 1),
    ]

    def __init__(self):
        self._stby = DigitalOutputDevice(DRUM_STBY_PIN, initial_value=False)
        self._in1  = DigitalOutputDevice(DRUM_IN1_PIN, initial_value=False)
        self._in2  = DigitalOutputDevice(DRUM_IN2_PIN, initial_value=False)
        self._in3  = DigitalOutputDevice(DRUM_IN3_PIN, initial_value=False)
        self._in4  = DigitalOutputDevice(DRUM_IN4_PIN, initial_value=False)
        self._step_index = 0
        self.current_slot = SLOT_RED  # Assumes manual pre-alignment

    def _set_coils(self, state):
        self._in1.value = bool(state[0])
        self._in2.value = bool(state[1])
        self._in3.value = bool(state[2])
        self._in4.value = bool(state[3])

    def _release_coils(self):
        """De-energise all coils to reduce heat when not stepping."""
        self._set_coils((0, 0, 0, 0))

    def _step_forward(self):
        self._stby.on()
        self._step_index = (self._step_index + 1) % 8
        self._set_coils(self.HALF_STEP[self._step_index])
        time.sleep(DRUM_STEP_DELAY_SEC)

    def _rotate_steps(self, steps):
        for _ in range(steps):
            self._step_forward()
        self._release_coils()
        self._stby.off()

    def rotate_to(self, target_slot):
        """Rotate clockwise by the minimum steps to reach target_slot."""
        delta = (target_slot - self.current_slot) % 4
        if delta == 0:
            return
        self._rotate_steps(delta * DRUM_STEPS_PER_SLOT)
        self.current_slot = target_slot

    def load(self):
        """
        Ramp lifts to tip one patient into the compartment currently
        facing the loading ramp. Call AFTER rotate_to(target_slot).
        Ramp control happens in RampServo — this just marks time.
        """
        pass  # Ramp servo is called from PatientRobot.collect_patient()

    def unload(self, slot):
        """Rotate to slot then open trapdoor (trapdoor handled by servo)."""
        self.rotate_to(slot)
        # Trapdoor servo call happens in PatientRobot.deliver()


# ====================================================================
# SECTION 9: RAMP SERVO (direct Pi GPIO hardware PWM)
# ====================================================================

class RampServo:
    """
    Controls the loading ramp.
    Uses gpiozero.Servo on RAMP_SERVO_PIN.
    Positions: -1.0 = fully closed, +1.0 = fully open (tune these).
    See CONFLICT 1 at top of file re: PWM pin availability.
    """

    def __init__(self):
        self._servo = Servo(RAMP_SERVO_PIN)

    def open(self):
        self._servo.value = RAMP_SERVO_OPEN
        time.sleep(RAMP_MOVE_TIME_SEC)

    def close(self):
        self._servo.value = RAMP_SERVO_CLOSED
        time.sleep(RAMP_MOVE_TIME_SEC)

    def detach(self):
        self._servo.detach()


# ====================================================================
# SECTION 10: NAVIGATION
# ====================================================================

class Navigation:
    """
    Encoder + line-sensor + ToF based navigation.
    No IMU. Turns use timed pivots — tune TURN_90_SEC / TURN_180_SEC.
    All checkpoints have retry logic and degrade gracefully rather
    than raising exceptions that kill the match.
    """

    def __init__(self, drive, lines, tof):
        self.drive = drive
        self.lines = lines
        self.tof   = tof
        self._start_time = None

    def start_timer(self):
        self._start_time = time.monotonic()

    def time_remaining(self):
        if self._start_time is None:
            return COMPETITION_TIME_SEC
        return COMPETITION_TIME_SEC - (time.monotonic() - self._start_time)

    def _time_ok(self):
        return self.time_remaining() > 2.0

    def reset_checkpoint(self):
        self.drive.reset_encoders()

    def line_checkpoint(self):
        """
        Drive forward slowly until all IR sensors see black simultaneously.
        Retries up to LINE_RETRIES times. On final failure, stops and
        continues the mission rather than crashing — a missed line crossing
        means the robot is slightly off but still functional.
        """
        for attempt in range(LINE_RETRIES):
            debounce = 0
            start = time.monotonic()
            while time.monotonic() - start < LINE_TIMEOUT_SEC:
                if not self._time_ok():
                    self.drive.stop()
                    return False
                if self.lines.all_high():
                    debounce += 1
                    if debounce >= LINE_DEBOUNCE:
                        self.drive.stop()
                        self.reset_checkpoint()
                        time.sleep(0.1)
                        return True
                else:
                    debounce = 0
                self.drive.forward(0.30)
                time.sleep(0.005)

            # Timeout on this attempt: nudge forward and retry
            self.drive.stop()
            if attempt < LINE_RETRIES - 1:
                self.drive.forward(0.15)
                time.sleep(0.15)
                self.drive.stop()

        # All retries failed: log and continue
        print("[WARN] line_checkpoint: failed after retries, continuing")
        self.drive.stop()
        self.reset_checkpoint()
        return False

    def wall_checkpoint(self, use_side=False):
        """
        Drive forward until a ToF sensor reads near-wall.
        Retries up to WALL_RETRIES times. On final failure, stops
        where it is and continues — a missed wall stop means slightly
        wrong position, not a match-ending crash.
        """
        reader = self.tof.side_near_wall if use_side else self.tof.front_near_wall

        for attempt in range(WALL_RETRIES):
            start = time.monotonic()
            while time.monotonic() - start < TOF_TIMEOUT_SEC:
                if not self._time_ok():
                    self.drive.stop()
                    return False
                if reader():
                    self.drive.stop()
                    self.reset_checkpoint()
                    time.sleep(0.05)
                    return True
                self.drive.forward(0.25)
                time.sleep(0.01)

            self.drive.stop()
            if attempt < WALL_RETRIES - 1:
                time.sleep(0.15)

        print("[WARN] wall_checkpoint: failed after retries, continuing")
        self.drive.stop()
        self.reset_checkpoint()
        return False

    def drive_distance(self, distance_mm, speed=None, reverse=False):
        """
        Drive a fixed distance using encoder averaging.
        Applies a small left/right correction to reduce drift.
        Has a hard timeout to prevent infinite loops if encoders fail.
        """
        if distance_mm <= 0:
            return True

        spd = speed or (REVERSE_SPEED if reverse else FORWARD_SPEED)
        direction = -1 if reverse else 1
        self.reset_checkpoint()
        start = time.monotonic()

        while self.drive.distance_mm() < distance_mm:
            if not self._time_ok():
                break
            if time.monotonic() - start > MOVE_TIMEOUT_SEC:
                print(f"[WARN] drive_distance: timeout at "
                      f"{self.drive.distance_mm():.0f}mm / {distance_mm}mm")
                break

            left  = self.drive.left_distance_mm()
            right = self.drive.right_distance_mm()
            correction = (left - right) * 0.01
            l_spd = max(0.0, min(MAX_SPEED, spd - correction))
            r_spd = max(0.0, min(MAX_SPEED, spd + correction))
            self.drive._set(direction * l_spd, direction * r_spd)
            time.sleep(0.005)

        self.drive.stop()
        self.reset_checkpoint()
        return True

    def turn_right_90(self):
        """Timed 90-degree clockwise pivot. Tune TURN_90_SEC."""
        if TURN_90_SEC <= 0:
            print("[WARN] TURN_90_SEC not set, skipping turn")
            return
        start = time.monotonic()
        while time.monotonic() - start < TURN_90_SEC:
            self.drive.turn_right()
            time.sleep(0.01)
        self.drive.stop()
        time.sleep(0.1)

    def turn_left_90(self):
        """Timed 90-degree counter-clockwise pivot."""
        if TURN_90_SEC <= 0:
            print("[WARN] TURN_90_SEC not set, skipping turn")
            return
        start = time.monotonic()
        while time.monotonic() - start < TURN_90_SEC:
            self.drive.turn_left()
            time.sleep(0.01)
        self.drive.stop()
        time.sleep(0.1)

    def turn_180(self):
        """Timed 180-degree pivot."""
        if TURN_180_SEC <= 0:
            print("[WARN] TURN_180_SEC not set, skipping turn")
            return
        start = time.monotonic()
        while time.monotonic() - start < TURN_180_SEC:
            self.drive.turn_right()
            time.sleep(0.01)
        self.drive.stop()
        time.sleep(0.1)


# ====================================================================
# SECTION 11: PATIENT ROBOT MISSION
# ====================================================================

class PatientRobot:
    """
    Mission sequence for CR8S (Robot 1 / crates.py).

    Drum pre-loaded: slot 1 = 6 kits (red/hospital),
                     slot 2 = 2 kits (yellow/PCC1),
                     slot 3 = 2 kits (yellow/PCC2),
                     slot 4 = 0 kits (green/RZ).
    Drum manually set to slot 1 before match start.

    Yellow fill rule: first 2 yellows → slot 2, next 2 → slot 3.
    """

    def __init__(self):
        require_configuration()

        self.drive  = DriveSystem()
        self.lines  = LineSensors()
        self.tof    = ToFSensors()
        self.color  = ColorSensor()
        self.drum   = Drum()
        self.ramp   = RampServo()
        self.nav    = Navigation(self.drive, self.lines, self.tof)

        self._yellow_count = 0  # Tracks yellows sorted so far (0-3)

    def _slot_for_color(self, color):
        if color == "red":
            return SLOT_RED
        if color == "green":
            return SLOT_GREEN
        if color == "yellow":
            # First 2 yellows → PCC1, next 2 → PCC2
            slot = SLOT_YELLOW_PCC1 if self._yellow_count < 2 else SLOT_YELLOW_PCC2
            self._yellow_count += 1
            return slot
        return None  # Unknown color

    def _read_color(self):
        """Read with retries. Returns color string or None."""
        for _ in range(COLOR_RETRIES):
            color = self.color.read()
            if color is not None:
                return color
            time.sleep(0.05)
        return None

    def collect_patient(self):
        """
        At a patient position: read color, rotate drum, load via ramp.
        On color failure: skip this patient and move on (do not crash).
        """
        color = self._read_color()
        if color is None:
            print("[WARN] collect_patient: color read failed, skipping")
            return

        slot = self._slot_for_color(color)
        if slot is None:
            print(f"[WARN] collect_patient: unrecognised color '{color}', skipping")
            return

        print(f"[INFO] Patient: {color} → slot {slot}")
        self.drum.rotate_to(slot)
        self.ramp.open()
        time.sleep(0.2)   # Patient slides into drum
        self.ramp.close()

    def deliver(self, slot, drive_action, reverse_action=None):
        """
        Generic delivery step:
          1. Drive to zone (drive_action is a callable).
          2. Unload that drum slot (opens trapdoor — you need a trapdoor
             servo here once mechanism is finalised).
          3. Reverse out (reverse_action is a callable, or just reverses).
        Trapdoor servo is not implemented yet — add it once the mechanism
        is confirmed (see TODO:MECHANISM below).
        """
        drive_action()
        # TODO:MECHANISM — open trapdoor servo, wait, close it.
        # Until the trapdoor servo is wired and calibrated, nothing
        # will physically come out. Add:
        #   self.trapdoor.open()
        #   time.sleep(0.5)
        #   self.trapdoor.close()
        print(f"[INFO] Delivering slot {slot}")
        if reverse_action:
            reverse_action()

    def run(self):
        """
        Full mission sequence.
        All distances are macros — set them before running.
        Turn directions assume starting orientation facing up the field.
        """
        try:
            self.drive.enable()
            self.nav.start_timer()
            self.ramp.close()

            # --------------------------------------------------------
            # PHASE 1: Cross starting line
            # Drive forward until all IR sensors see the starting line
            # tape (all-high), then turn right to face the patient area.
            # --------------------------------------------------------
            self.nav.line_checkpoint()
            self.nav.turn_right_90()

            # --------------------------------------------------------
            # PHASE 2: U-path collecting all 12 patients
            # PATIENT_ROUTE_MM defines distances between consecutive
            # patient positions. The path includes the turns between
            # rows — encode a 0mm entry for any stop that is just a
            # turn with no patient (or add explicit turn calls here).
            #
            # TODO:MEASURE all 12 entries in PATIENT_ROUTE_MM.
            # TODO:VERIFY this loop matches the physical layout.
            # --------------------------------------------------------
            for i, dist_mm in enumerate(PATIENT_ROUTE_MM):
                self.nav.drive_distance(dist_mm)
                self.collect_patient()

            # After 6th patient (right side done), turn around:
            # TODO:TUNE this turn timing / position in the route.
            self.nav.turn_180()

            # Continue collecting remaining 6 patients (left side).
            # NOTE: The single loop above treats all 12 legs identically.
            # If your U-path requires a turn mid-loop (between right-side
            # and left-side patients), add the turn call at the right index
            # here, or split into two loops of 6.

            # --------------------------------------------------------
            # PHASE 3: Line crossing = board halfway mark detected
            # Robot should now be facing toward the delivery zone.
            # --------------------------------------------------------
            self.nav.line_checkpoint()  # First mid-board crossing
            self.nav.turn_left_90()
            self.nav.line_checkpoint()  # Back to right side
            self.nav.turn_right_90()

            # --------------------------------------------------------
            # PHASE 4: Deliver to PCC1 (right side)
            # --------------------------------------------------------
            self.deliver(
                SLOT_YELLOW_PCC1,
                drive_action=lambda: self.nav.drive_distance(DIST_TO_PCC1_MM),
                reverse_action=lambda: self.nav.drive_distance(
                    DIST_BACK_FROM_PCC1_MM, reverse=True),
            )

            # --------------------------------------------------------
            # PHASE 5: Deliver to Hospital (centre)
            # --------------------------------------------------------
            self.nav.turn_left_90()
            self.deliver(
                SLOT_RED,
                drive_action=lambda: self.nav.drive_distance(DIST_TO_HOSPITAL_MM),
                reverse_action=lambda: self.nav.drive_distance(
                    DIST_BACK_FROM_HOSP_MM, reverse=True),
            )

            # --------------------------------------------------------
            # PHASE 6: Deliver to PCC2 (left side)
            # --------------------------------------------------------
            self.nav.turn_right_90()
            self.nav.wall_checkpoint()  # Align against far wall
            self.nav.turn_right_90()
            self.deliver(
                SLOT_YELLOW_PCC2,
                drive_action=lambda: self.nav.drive_distance(DIST_TO_PCC2_MM),
                reverse_action=lambda: self.nav.drive_distance(
                    DIST_BACK_FROM_PCC2_MM, reverse=True),
            )

            # --------------------------------------------------------
            # PHASE 7: Return to starting zone, deliver green patients
            # --------------------------------------------------------
            self.nav.drive_distance(0, reverse=True)  # TODO:MEASURE
            self.nav.line_checkpoint()  # Half-board marker
            self.nav.turn_right_90()
            self.nav.wall_checkpoint()  # Starting zone wall
            self.nav.turn_right_90()
            self.deliver(
                SLOT_GREEN,
                drive_action=lambda: self.nav.drive_distance(DIST_TO_RZ_MM),
            )

            print("[INFO] Mission complete")

        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            self.drive.stop()
            self.drive.disable()
            self.ramp.detach()
            self._release_drum()

    def _release_drum(self):
        """De-energise drum coils on shutdown."""
        try:
            self.drum._release_coils()
            self.drum._stby.off()
        except Exception:
            pass


def main():
    robot = PatientRobot()
    robot.run()


if __name__ == "__main__":
    main()
