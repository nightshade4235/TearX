![TearX](assets/tearx.jpeg)

# CODE FOR THE ROBOTS

### crates.py | CR8S

- Collects the patients and sorts them into groups of 2, 2, 4, 4 for yellow part 1, yellow part 2, red and green respectively.
- Is loaded with the medkits in the arrangement 2, 2, 6, 0 for yellow part 1, yellow part 2, red and green respectively.
- Sends two yellows inot each PCC with 2 medkits each.
- Sends four reds to the hospital with 6 medkits.
- Sends four greens to the starting zone with no medkits.

### galileo.py | GALILEO

- Collects and stores the samples
- Distributes the samples in the lab
- Puts walls into place and locks itself inside

- Below is a **clean proposed wiring plan** for the Raspberry Pi 4, assuming:

- No active cooling fan using GPIO.
- Two TB6612FNG boards control the four N20 motors.
- Each encoder has A/B outputs.
- The servo is controlled through the Raspberry Pi Servo HAT.
- I²C uses GPIO 2 and 3.
- The stepper uses a dedicated **STEP/DIR driver**.
- The RLS08 inputs use an I²C GPIO expander because the Pi does not have enough direct GPIO pins for everything.

This is a proposed layout, not a substitute for checking the actual driver pin labels.

# 1. Raspberry Pi power and I²C

| Raspberry Pi function | BCM GPIO / pin |
|---|---:|
| I²C SDA | GPIO 2 / physical pin 3 |
| I²C SCL | GPIO 3 / physical pin 5 |
| Pi 5 V input | Physical pin 2 or 4 |
| Pi ground | Any ground pin |

The following share the I²C bus:

- Servo HAT.
- TCS34725 color sensor.
- VL53L0X sensors.
- GPIO expander for the IR arrays.

Each device must have a unique I²C address.

---

# 2. TB6612FNG motor drivers

Each TB6612FNG controls two motors.

## TB6612FNG number 1

| TB6612 pin | Function | BCM GPIO |
|---|---|---:|
| PWMA | Left-front motor PWM | GPIO 12 |
| AIN1 | Left-front direction 1 | GPIO 5 |
| AIN2 | Left-front direction 2 | GPIO 6 |
| PWMB | Left-rear motor PWM | GPIO 13 |
| BIN1 | Left-rear direction 1 | GPIO 16 |
| BIN2 | Left-rear direction 2 | GPIO 20 |
| STBY | Driver enable | GPIO 21 |

## TB6612FNG number 2

| TB6612 pin | Function | BCM GPIO |
|---|---|---:|
| PWMA | Right-front motor PWM | GPIO 18 |
| AIN1 | Right-front direction 1 | GPIO 23 |
| AIN2 | Right-front direction 2 | GPIO 24 |
| PWMB | Right-rear motor PWM | GPIO 19 |
| BIN1 | Right-rear direction 1 | GPIO 25 |
| BIN2 | Right-rear direction 2 | GPIO 26 |
| STBY | Driver enable | GPIO 27 |

## TB6612 power connections

For each TB6612FNG:

```text
VM     → motor supply
VCC    → regulated logic supply recommended by the board documentation
GND    → common ground
STBY   → assigned Pi GPIO
AO1/AO2 → one N20 motor
BO1/BO2 → one N20 motor
```

The Pi GPIO pins provide **control signals only**. They must not power the motors.

The TB6612 logic voltage and motor voltage must be checked against the actual breakout boards. Do not assume the battery connects directly to every terminal.

---

# 3. N20 motor connections

| Motor | Driver channel |
|---|---|
| Left front | TB6612 #1 channel A |
| Left rear | TB6612 #1 channel B |
| Right front | TB6612 #2 channel A |
| Right rear | TB6612 #2 channel B |

Each motor connects only to its driver output pair:

```text
Motor wire 1 → AO1/AO2 or BO1/BO2
Motor wire 2 → other output terminal
```

If a motor’s forward direction is reversed, correct it in software or swap that motor’s two output wires.

---

# 4. Encoder connections

This assumes each encoder has four wires:

```text
VCC
GND
Encoder A
Encoder B
```

| Motor | Encoder A | Encoder B |
|---|---:|---:|
| Left front | GPIO 4 | GPIO 7 |
| Left rear | GPIO 8 | GPIO 9 |
| Right front | GPIO 10 | GPIO 11 |
| Right rear | GPIO 14 | GPIO 15 |

Encoder power:

```text
Encoder VCC → verified encoder supply
Encoder GND → common ground
Encoder A/B → Raspberry Pi GPIO inputs
```

Important:

- Confirm encoder outputs are safe for Raspberry Pi **3.3 V GPIO**.
- Do not connect a 5 V encoder signal directly to a Pi GPIO.
- Confirm whether the encoder board already includes pull-up resistors.
- Use edge interrupts/callbacks rather than slow polling.
- The encoder pulses-per-wheel-revolution still need to be measured.

---

# 5. IR arrays

The Pi does not have enough spare direct GPIO pins for both full encoder quadrature and eight IR inputs.

Use an I²C GPIO expander, such as an MCP23017, for the RLS08 inputs.

## MCP23017 connection

| MCP23017 pin/function | Connection |
|---|---|
| VDD | 3.3 V |
| VSS | Common ground |
| SDA | Pi GPIO 2 |
| SCL | Pi GPIO 3 |
| RESET | 3.3 V through the required pull-up |
| A0/A1/A2 | Set address as required |

## Suggested IR assignment on the expander

| Expander input | Function |
|---|---|
| GPA0 | Left IR 1 |
| GPA1 | Left IR 2 |
| GPA2 | Left IR 3 |
| GPA3 | Left IR 4 |
| GPA4 | Right IR 1 |
| GPA5 | Right IR 2 |
| GPA6 | Right IR 3 |
| GPA7 | Right IR 4 |

Your confirmed logic is:

```text
Black line = LOW
White surface = HIGH
```

In software:

```python
IR_ACTIVE_LOW = True
```

Before soldering, confirm how many outputs the RLS08 board actually provides. If each array has a different number of outputs, the expander assignment must be adjusted.

---

# 6. ToF sensors

Use the I²C bus for both VL53L0X sensors.

| Function | BCM GPIO |
|---|---:|
| Front sensor XSHUT | GPIO 17 |
| Side sensor XSHUT | GPIO 22 |

Normal I²C connections:

```text
VL53L0X SDA → Pi GPIO 2
VL53L0X SCL → Pi GPIO 3
VL53L0X GND → common ground
VL53L0X VCC → sensor-compatible supply
```

Startup sequence:

```text
1. Hold both XSHUT pins LOW.
2. Enable the front sensor.
3. Assign it a new I²C address.
4. Enable the side sensor.
5. Assign it a different I²C address.
```

Example addresses:

```python
TOF_FRONT_ADDRESS = 0x30
TOF_SIDE_ADDRESS = 0x31
```

Check the actual CircuitPython library and breakout-board behavior before using those addresses.

---

# 7. TCS34725 color sensor

The color sensor also uses I²C:

| TCS34725 pin | Connection |
|---|---|
| SDA | Pi GPIO 2 |
| SCL | Pi GPIO 3 |
| GND | Common ground |
| VCC | Sensor-compatible supply |

Its I²C address must not conflict with:

- Servo HAT.
- VL53L0X sensors.
- GPIO expander.

The sensor should be physically positioned and calibrated before finalizing the red, yellow, and green thresholds.

---

# 8. Servo HAT and ramp servo

The ramp servo does **not** need a direct Pi PWM GPIO.

| Servo HAT connection | Connection |
|---|---|
| HAT SDA | Pi GPIO 2 |
| HAT SCL | Pi GPIO 3 |
| HAT logic ground | Common ground |
| HAT servo power | Separate regulated 5 V supply |
| Ramp servo signal | One HAT channel |

Example:

```python
RAMP_SERVO_CHANNEL = 0
```

The HAT channel number is not a Raspberry Pi GPIO number.

Confirm:

- Actual HAT I²C address.
- Servo channel.
- Safe closed angle.
- Safe open angle.
- Whether the 5 V supply can handle the servo’s startup and stall current.

Do not power an MG996/MG995-class servo from the Pi’s 5 V rail unless the power supply is specifically rated for it.

---

# 9. Stepper motor

The two TB6612FNG boards are already allocated to the four N20 motors. Do **not** connect the stepper to those same motor outputs.

Use a separate stepper driver.

## If the stepper driver uses STEP/DIR

| Function | BCM GPIO |
|---|---:|
| Stepper STEP | GPIO 0 |
| Stepper DIR | GPIO 1 |
| Stepper ENABLE, if required | GPIO 28 is unavailable; use a GPIO-expander output or tie it according to the driver documentation |

GPIO 0 and GPIO 1 are usable but are associated with the UART function on some Pi configurations. Disable the serial console if necessary.

## If the stepper driver uses four coil inputs

Do not use the table above. A four-input driver needs:

```text
IN1
IN2
IN3
IN4
```

and should preferably be connected through the I²C GPIO expander or another dedicated controller.

The stepper section cannot be finalized until the driver type is known.

Record:

```text
Stepper model:
Stepper driver:
Stepper voltage:
Driver input type:
Steps per revolution:
Steps per drum slot:
```

For your logical drum control:

```python
delta = (target_slot - current_slot) % 4
```

The software can start with:

```python
current_slot = SLOT_RED
```

provided the drum is manually placed in the red-slot reference position before the match.

---

# 10. Emergency stop

Reserve a direct Pi input:

| Function | BCM GPIO |
|---|---:|
| Software E-stop input | GPIO 28 is unavailable; use GPIO 22 only if it is not used by the side ToF XSHUT, or use an expander input |

A better arrangement is:

```text
Physical E-stop → cuts motor power directly
Software E-stop → tells the Pi to stop sending motor commands
```

The software input must not be the only emergency-stop protection.

---

# Final GPIO summary

| BCM GPIO | Assigned function |
|---:|---|
| 0 | Stepper STEP, if STEP/DIR driver |
| 1 | Stepper DIR, if STEP/DIR driver |
| 2 | I²C SDA |
| 3 | I²C SCL |
| 4 | Left-front encoder A |
| 5 | TB1 left-front AIN1 |
| 6 | TB1 left-front AIN2 |
| 7 | Left-front encoder B |
| 8 | Left-rear encoder A |
| 9 | Left-rear encoder B |
| 10 | Right-front encoder A |
| 11 | Right-front encoder B |
| 12 | TB1 left-front PWMA |
| 13 | TB1 left-rear PWMB |
| 14 | Right-rear encoder A |
| 15 | Right-rear encoder B |
| 16 | TB1 left-rear BIN1 |
| 17 | Front ToF XSHUT |
| 18 | TB2 right-front PWMA |
| 19 | TB2 right-rear PWMB |
| 20 | TB1 left-rear BIN2 |
| 21 | TB1 STBY |
| 22 | Side ToF XSHUT |
| 23 | TB2 right-front AIN1 |
| 24 | TB2 right-front AIN2 |
| 25 | TB2 right-rear BIN1 |
| 26 | TB2 right-rear BIN2 |
| 27 | TB2 STBY |

The IR sensors use the I²C GPIO expander rather than direct Pi GPIOs.

## Final pre-solder checks

Before soldering, verify only these remaining points:

1. The two TB6612FNG boards accept this control arrangement.
2. The encoder outputs are 3.3 V-safe.
3. The RLS08 array output count matches the expander plan.
4. The stepper driver is identified.
5. The servo HAT address and channel are known.
6. The 5 V servo supply is powerful enough.
7. The physical emergency-stop cuts motor power.

---

# newer wiring 

# CR8S (Robot 1) — Wiring Reference
**TearX ST59 | crates.py**
Last updated: 2026-10-04
 
---
 
## Status key
- ✅ Confirmed in code, assumed correct
- ⚠️ Needs verification before soldering
- ❌ Not yet decided / blocking
---
 
## 1. Raspberry Pi 4 — I2C bus
 
All I2C devices share GPIO 2 (SDA) and GPIO 3 (SCL).
 
| Device | I2C Address | Status |
|---|---|---|
| TCS34725 color sensor | 0x29 (fixed, cannot change) | ⚠️ Verify no conflict |
| VL53L0X front ToF | 0x30 (assigned at boot via XSHUT) | ✅ |
| VL53L0X side ToF | 0x31 (assigned at boot via XSHUT) | ✅ |
| Servo HAT | NOT on this robot | ✅ confirmed removed |
 
---
 
## 2. GPIO pin assignments
 
| BCM GPIO | Physical Pin | Assigned to | Status |
|---:|---:|---|---|
| 0 | 27 | Drum stepper STEP or IN1 — see Section 6 | ❌ NEEDS WIRE |
| 1 | 28 | Drum stepper DIR or IN2 — see Section 6 | ❌ NEEDS WIRE |
| 2 | 3 | I2C SDA (shared bus) | ✅ |
| 3 | 5 | I2C SCL (shared bus) | ✅ |
| 4 | 7 | Left-front encoder A | ✅ |
| 5 | 29 | TB6612 #1 — left-front AIN1 | ✅ |
| 6 | 31 | TB6612 #1 — left-front AIN2 | ✅ |
| 7 | 26 | Left-front encoder B | ⚠️ Only if enough pins free |
| 8 | 24 | Left-rear encoder A | ✅ |
| 9 | 21 | Left-rear encoder B | ⚠️ Only if enough pins free |
| 10 | 19 | Right-front encoder A | ✅ |
| 11 | 23 | Right-front encoder B | ⚠️ Only if enough pins free |
| 12 | 32 | TB6612 #1 — left-front PWMA | ✅ (hardware PWM) |
| 13 | 33 | TB6612 #1 — left-rear PWMB | ✅ (hardware PWM) |
| 14 | 8 | Right-rear encoder A | ✅ |
| 15 | 22 | Right-rear encoder B | ⚠️ Only if enough pins free |
| 16 | 36 | TB6612 #1 — left-rear BIN1 | ✅ |
| 17 | 11 | VL53L0X front — XSHUT | ✅ |
| 18 | 12 | TB6612 #2 — right-front PWMA | ✅ (hardware PWM) |
| 19 | 35 | TB6612 #2 — right-rear PWMB | ✅ (hardware PWM) |
| 20 | 38 | TB6612 #1 — left-rear BIN2 | ✅ |
| 21 | 40 | TB6612 #1 — STBY | ✅ |
| 22 | 15 | VL53L0X side — XSHUT | ✅ |
| 23 | 16 | TB6612 #2 — right-front AIN1 | ✅ |
| 24 | 18 | TB6612 #2 — right-front AIN2 | ✅ |
| 25 | 22 | TB6612 #2 — right-rear BIN1 | ✅ |
| 26 | 37 | TB6612 #2 — right-rear BIN2 | ✅ |
| 27 | 13 | TB6612 #2 — STBY | ✅ |
| — | — | Ramp servo signal | ❌ NO PIN AVAILABLE — see Conflict 1 |
| — | — | Drum stepper IN3 / IN4 | ❌ NO PIN AVAILABLE — see Conflict 2 |
| — | — | IR array pins (up to 8) | ❌ NO PINS AVAILABLE — see Conflict 3 |
| — | — | Emergency stop | ❌ NOT WIRED — see Conflict 4 |
 
---
 
## 3. TB6612FNG #1 — Left motors
 
**Controls:** Left-front (channel A) and Left-rear (channel B)
 
| TB6612 Pin | Connects to | BCM GPIO |
|---|---|---:|
| PWMA | Left-front motor PWM | 12 |
| AIN1 | Left-front direction 1 | 5 |
| AIN2 | Left-front direction 2 | 6 |
| PWMB | Left-rear motor PWM | 13 |
| BIN1 | Left-rear direction 1 | 16 |
| BIN2 | Left-rear direction 2 | 20 |
| STBY | Driver enable | 21 |
| VM | Motor supply (~12V from battery) | — |
| VCC | Logic supply (3.3V or 5V per board spec) | — |
| GND | Common ground | — |
| AO1/AO2 | Left-front motor wires | — |
| BO1/BO2 | Left-rear motor wires | — |
 
**Motor direction:** If a motor runs backwards, swap its two output wires
(AO1↔AO2 or BO1↔BO2), do not change code.
 
---
 
## 4. TB6612FNG #2 — Right motors
 
**Controls:** Right-front (channel A) and Right-rear (channel B)
 
| TB6612 Pin | Connects to | BCM GPIO |
|---|---|---:|
| PWMA | Right-front motor PWM | 18 |
| AIN1 | Right-front direction 1 | 23 |
| AIN2 | Right-front direction 2 | 24 |
| PWMB | Right-rear motor PWM | 19 |
| BIN1 | Right-rear direction 1 | 25 |
| BIN2 | Right-rear direction 2 | 26 |
| STBY | Driver enable | 27 |
| VM | Motor supply (~12V) | — |
| VCC | Logic supply | — |
| GND | Common ground | — |
| AO1/AO2 | Right-front motor wires | — |
| BO1/BO2 | Right-rear motor wires | — |
 
---
 
## 5. N20 encoders (one per wheel)
 
Each encoder has 4 wires: VCC, GND, A, B.
 
| Motor | Encoder A (BCM) | Encoder B (BCM) | Notes |
|---|---:|---:|---|
| Left-front | 4 | 7 | B only if pin available |
| Left-rear | 8 | 9 | B only if pin available |
| Right-front | 10 | 11 | B only if pin available |
| Right-rear | 14 | 15 | B only if pin available |
 
⚠️ **Encoder VCC must be 3.3V** — do not connect 5V encoder output
directly to Pi GPIO. Check your N20 encoder board's output voltage.
If it outputs 5V signals, add a voltage divider or level shifter.
 
⚠️ **ENCODER_CPR must be measured** — count pulses for one full wheel
revolution by hand before the first test run. Common N20 values are
7–12 PPR × gear ratio. Put the result in `ENCODER_CPR` in crates.py.
 
---
 
## 6. Drum stepper (28BYJ-48 via TB6612FNG #3)
 
The 28BYJ-48 is a 4-phase unipolar stepper driven by coil sequence,
not STEP/DIR. One dedicated TB6612FNG drives it using all 4 control
pins as coil inputs.
 
**Wiring:**
 
| TB6612 Pin | 28BYJ-48 | BCM GPIO |
|---|---|---:|
| AIN1 | Coil IN1 (blue wire) | ❌ TODO:WIRE |
| AIN2 | Coil IN2 (pink wire) | ❌ TODO:WIRE |
| BIN1 | Coil IN3 (yellow wire) | ❌ TODO:WIRE |
| BIN2 | Coil IN4 (orange wire) | ❌ TODO:WIRE |
| STBY | Driver enable | ❌ TODO:WIRE |
| VM | Stepper supply (5V typical for 28BYJ-48) | — |
| VCC | Logic supply | — |
| GND | Common ground | — |
 
**⚠️ CONFLICT 2 — GPIO shortage:**
All standard Pi GPIO pins are used by motors, encoders, and I2C.
Options:
- a) Use GPIO 0 and 1 (UART pins — disable serial console first)
  plus two more from the encoder B pins if those are not wired
- b) Use an I2C GPIO expander (MCP23017) for the drum coil pins
- c) Use a dedicated stepper controller (e.g. ULN2003 board with
  its own microcontroller) and communicate over UART or I2C
**Drum slot order (physical, looking from above):**
```
 1  2
 4  3
```
Rotation formula: `delta = (target - current) % 4` clockwise steps.
Drum must be manually pre-aligned to slot 1 before each match.
Slot 1 = red/hospital position (facing the loading ramp).
 
**Steps:** 28BYJ-48 half-step = 4096 steps/rev → 1024 steps/slot.
Full-step = 2048 steps/rev → 512 steps/slot.
Confirm which mode your driver uses.
 
---
 
## 7. IR line sensor arrays
 
**Confirmed behavior: black line = LOW, white surface = HIGH**
 
Two arrays of 4 sensors each (8 total).
 
| Array | Sensor | BCM GPIO | Status |
|---|---|---:|---|
| Left | IR 1 | ❌ TODO:WIRE | No pins available |
| Left | IR 2 | ❌ TODO:WIRE | No pins available |
| Left | IR 3 | ❌ TODO:WIRE | No pins available |
| Left | IR 4 | ❌ TODO:WIRE | No pins available |
| Right | IR 1 | ❌ TODO:WIRE | No pins available |
| Right | IR 2 | ❌ TODO:WIRE | No pins available |
| Right | IR 3 | ❌ TODO:WIRE | No pins available |
| Right | IR 4 | ❌ TODO:WIRE | No pins available |
 
**⚠️ CONFLICT 3 — GPIO shortage (BLOCKING):**
With full encoder quadrature (8 pins) + all motor/STBY pins used,
there are no free GPIO pins for 8 IR inputs.
 
**Options (pick one before soldering):**
- a) **Drop encoder B pins** (use single-edge counting, half resolution
  but still functional for distance). Frees 4 pins → still 4 short.
- b) **MCP23017 I2C GPIO expander** — connects via I2C (GPIO 2/3),
  provides 16 extra GPIO pins. Best solution, needs the MCP23017 chip.
  Set I2C address via A0/A1/A2 jumpers (default 0x20).
- c) **Reduce IR count** — use 3 sensors per array instead of 4.
  Frees 2 pins, still short.
- d) **Combination of a + b** — drop all encoder B pins (frees 4),
  use remaining free pins for IR, expander for the rest.
**Recommendation: MCP23017 + drop encoder B pins.**
This is the cleanest solution and the one to implement before 7th.
 
---
 
## 8. VL53L0X ToF sensors
 
Both on I2C bus. XSHUT pins used to assign unique addresses at boot.
 
| Sensor | XSHUT GPIO | I2C Address after boot |
|---|---:|---|
| Front | 17 | 0x30 |
| Side | 22 | 0x31 |
 
**Boot sequence (already in code):**
1. Both XSHUT LOW (both sensors in reset)
2. Front XSHUT HIGH → assign address 0x30
3. Side XSHUT HIGH → assign address 0x31
Standard I2C connections:
```
VL53L0X VCC → 3.3V (check your breakout board)
VL53L0X GND → common ground
VL53L0X SDA → GPIO 2
VL53L0X SCL → GPIO 3
VL53L0X XSHUT → assigned GPIO above
```
 
---
 
## 9. TCS34725 color sensor
 
I2C device, fixed address 0x29 (cannot be changed).
 
```
TCS34725 VCC → 3.3V or 5V (check breakout board)
TCS34725 GND → common ground
TCS34725 SDA → GPIO 2
TCS34725 SCL → GPIO 3
TCS34725 LED → 3.3V or GPIO (to control the onboard LED)
```
 
⚠️ The TCS34725 address 0x29 must not conflict with other I2C devices.
Current devices: 0x29 (color), 0x30 (ToF front), 0x31 (ToF side).
No conflict. ✅
 
---
 
## 10. Ramp servo
 
**⚠️ CONFLICT 1 — PWM pin conflict (BLOCKING):**
The Pi's hardware PWM pins (GPIO 12, 13, 18, 19) are all used by
motor PWM signals. Software PWM on any other GPIO causes jitter.
 
**Options:**
- a) **Accept software PWM jitter** — the ramp only moves twice per
  patient (open/close) and doesn't hold position under load.
  Likely acceptable. Use any free GPIO with gpiozero.Servo().
- b) **Add a PCA9685 PWM board** — I2C device, provides 16 hardware
  PWM channels. Cleanest solution. Address 0x40 by default.
- c) **Remap one motor to free a hardware PWM pin** — complex, not
  recommended this close to competition.
`RAMP_SERVO_PIN = None` in crates.py — set this before running.
 
```
Servo VCC (red)    → 5V supply (NOT Pi 5V rail for MG995/MG996)
Servo GND (brown)  → common ground
Servo signal (orange/yellow) → assigned GPIO pin
```
 
---
 
## 11. Emergency stop
 
**❌ CONFLICT 4 — NOT WIRED (DISQUALIFICATION RISK):**
The rulebook requires a physically accessible emergency stop.
A referee may disqualify the robot before the match if none is present.
 
**Minimum implementation (30 minutes of work):**
```
Battery positive → fuse → rocker switch → motor driver VM pins
```
The switch physically cuts motor power. The Pi stays on.
This satisfies the rulebook requirement and takes one rocker switch
and two wire connections.
 
---
 
## 12. Power
 
| Rail | Voltage | Supplied to |
|---|---|---|
| Main battery | 12.8V (LiFePO4 4S1P) | Motor driver VM pins |
| Motor logic | 3.3V or 5V (check TB6612 VCC spec) | TB6612 VCC pins |
| Pi supply | 5V regulated | Pi USB-C or GPIO 5V pins |
| Servo supply | 5V regulated (separate from Pi) | Servo VCC |
| Encoder supply | 3.3V | Encoder VCC |
| Sensor supply | 3.3V or 5V (check each breakout) | VCC of each sensor |
 
⚠️ **All grounds must be common.** Battery GND, Pi GND, motor driver
GND, sensor GND — all connected together. A floating ground is the
most common cause of erratic sensor readings and servo jitter.
 
⚠️ **Do not power MG995/MG996 servos from the Pi's 5V pin.**
The Pi's 5V rail is limited to ~1A from USB power. A stalling servo
can draw 2A+. Use a separate 5V supply rated for at least 3A.
 
---
 
## 13. Open items before 7th October
 
| Item | Blocking? | Action needed |
|---|---|---|
| ENCODER_CPR | ✅ YES | Measure counts/rev on real motor today |
| TURN_90_SEC | ✅ YES | Time a 90-degree pivot on real surface |
| PATIENT_ROUTE_MM | ✅ YES | Measure 12 legs on real/practice field |
| IR GPIO pins | ✅ YES | Resolve CONFLICT 3, assign pins |
| Drum stepper GPIO | ✅ YES | Resolve CONFLICT 2, assign 4+1 pins |
| Ramp servo GPIO | ✅ YES | Resolve CONFLICT 1, assign pin |
| Trapdoor servo | ✅ YES | Wire, add to deliver() in code |
| Emergency stop | ✅ YES | Wire rocker switch in battery line |
| Encoder B pins | No | Single-edge works, add later |
| Color thresholds | No | Tune on real cylinders before match |
| DIST_TO_* macros | No | Measure on real field |

Do not connect the battery until the power wiring, grounds, fuse/switch arrangement, and regulator outputs have been checked with a multimeter.
