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
