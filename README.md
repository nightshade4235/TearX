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

Do not connect the battery until the power wiring, grounds, fuse/switch arrangement, and regulator outputs have been checked with a multimeter.
