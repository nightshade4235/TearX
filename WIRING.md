# Patient Robot — Complete Workings and Wiring Guide

**Project:** Robotics for Good Youth Challenge
**Robot:** Patient/medical-kit robot
**Primary architecture:** Raspberry Pi 4 master + ESP32 motor slave
**Status:** Assembly and calibration reference; verify all physical PCB assignments before final soldering.

> This document describes the intended working architecture. The Raspberry Pi makes all navigation decisions. The ESP32 only receives Pi commands, converts them into motor-driver signals, runs the requested action, and reports encoder readings back to the Pi.

---

## 1. What the robot must do

The patient robot is intended to:

- Collect 12 patients.

- Collect/manage 10 medical kits according to the game plan.

- Store patients in the drum compartments.

- Use the IR array to detect black tape/landmarks.

- Use the ToF sensor for approximate forward distance and wall/object proximity.

- Use the camera for patient alignment/orientation once the robot leaves the starting zone.

- Use the colour sensor only as a close-range colour confirmation if it can see the patient.

- Use servos for the ramp, sweeper, trapdoors, and medical-kit release.

- Use a stepper motor for the drum.

- Use four N20 encoder motors controlled by the ESP32.

The route is hardcoded in the Pi state machine. Exact route distances and timings must be measured on the real board.

---

## 2. Division of responsibility

### Raspberry Pi 4 — master

The Pi handles:

- IR sensor input.

- VL53L0X ToF input.

- MPU-6050 input.

- TCS34725 input.

- Camera input and patient alignment.

- Navigation state machine.

- Route decisions.

- Direction selection.

- Distance and turn calculations.

- Duration calculation for every motor action.

- Five servos.

- 28BYJ-48 drum stepper through ULN2003.

- UART commands to the ESP32.

- Encoder packets returned by the ESP32.

### ESP32 — motor slave

The ESP32 handles only low-level motor execution:

1. Receive a complete UART command from the Pi.

1. Validate its checksum.

1. Parse direction, speed, duration, and distance fields.

1. Convert the direction into four TB6612 motor outputs.

1. Run the motors for the Pi-provided duration.

1. Stop when the duration expires or when a stop command arrives.

1. Count encoder pulses.

1. Return encoder counts and status to the Pi.

The ESP32 does **not**:

- Choose the route.

- Search for patients.

- Decide where to turn.

- Calculate the route distance.

- Calculate the turn angle.

- Interpret the ToF, IR, colour, or camera sensors.

- Decide when a patient has been collected.

---

## 3. Raspberry Pi GPIO map

Pi software uses **BCM GPIO numbers**. Physical wiring uses **physical pin numbers**.

### Pi functions

| Function | BCM GPIO | Physical pin | Connection |
| --- | --- | --- | --- |
| Hardware I2C SDA | GPIO2 | 3 | VL53L0X + MPU-6050 SDA |
| Hardware I2C SCL | GPIO3 | 5 | VL53L0X + MPU-6050 SCL |
| UART TX | GPIO14 | 8 | ESP32 RX2 / GPIO16 |
| UART RX | GPIO15 | 10 | ESP32 TX2 / GPIO17 |
| Software I2C SDA | GPIO17 | 11 | TCS34725 SDA |
| Trapdoor 2 servo | GPIO18 | 12 | SG90 #2 signal |
| IR S2 | GPIO27 | 13 | IR array S2 |
| IR S3 | GPIO22 | 15 | IR array S3 |
| IR S4 | GPIO23 | 16 | IR array S4 |
| Stepper IN1 | GPIO4 | 7 | ULN2003 IN1 |
| Stepper IN2 | GPIO5 | 29 | ULN2003 IN2 |
| Stepper IN3 | GPIO6 | 31 | ULN2003 IN3 |
| Software I2C SCL | GPIO26 | 37 | TCS34725 SCL |
| Stepper IN4 | GPIO20 | 38 | ULN2003 IN4 |
| Ramp servo | GPIO12 | 32 | MG995 signal |
| Sweeper servo | GPIO13 | 33 | MG90S signal |
| Medical-kit servo | GPIO19 | 35 | MG995 signal |
| Trapdoor 1 servo | GPIO16 | 36 | SG90 #1 signal |
| Reserved/spare | GPIO21 | 40 | Future E-stop or spare |

### Pi power pins

| Physical pin | Function |
| --- | --- |
| 1 | 3.3 V sensor rail |
| 6 | Common ground |
| 17 | Optional additional 3.3 V |
| 26 | Optional additional ground |

> The custom PCB rails are only parallel connection points. They do not regulate voltage.

---

## 4. Raspberry Pi sensors

### 4.1 IR array

Only one IR array is used. Only S2, S3, and S4 are used by the software.

| IR pin | Pi physical pin | Pi BCM GPIO |
| --- | --- | --- |
| S2 | 13 | GPIO27 |
| S3 | 15 | GPIO22 |
| S4 | 16 | GPIO23 |
| VCC | 1 or 17 | 3.3 V |
| GND | 6 | GND |

Leave disconnected:

```
S1
S5, if present
CLP
NEAR
second IR array
```

Current interpretation:

```
1 = black/active
0 = white/not active
```

The physical left/right orientation must be verified:

```
S2 = left
S3 = centre/forward
S4 = right
```

### 4.2 VL53L0X ToF

Use one VL53L0X on hardware I2C bus 1.

```
VL53L0X VIN/VCC -> Pi 3.3 V, physical pin 1
VL53L0X GND     -> Pi GND, physical pin 6
VL53L0X SDA     -> Pi SDA, physical pin 3 / GPIO2
VL53L0X SCL     -> Pi SCL, physical pin 5 / GPIO3
```

Expected address:

```
0x29 on I2C bus 1
```

The ToF provides approximate distance in millimetres. It is used to detect that the robot is close to an object/wall. The practical minimum reading may be around 30–40 mm rather than zero.

### 4.3 MPU-6050

```
MPU VCC -> Pi 3.3 V, physical pin 1
MPU GND -> Pi GND, physical pin 6
MPU SDA -> Pi SDA, physical pin 3 / GPIO2
MPU SCL -> Pi SCL, physical pin 5 / GPIO3
MPU AD0 -> GND if using address 0x68
```

Expected address:

```
0x68 on I2C bus 1
```

The sensor must be woken from sleep before reading its registers. It can provide gyro/acceleration data, but heading and turn calibration are not complete yet.

### 4.4 TCS34725/CJMCU-34725 colour sensor

The colour sensor normally uses address `0x29`, which conflicts with the VL53L0X. It therefore uses a separate software I2C bus.

```
TCS VCC -> Pi 3.3 V, physical pin 1
TCS GND -> Pi GND, physical pin 6
TCS SDA -> Pi GPIO17, physical pin 11
TCS SCL -> Pi GPIO26, physical pin 37
TCS INT -> leave disconnected
TCS LED -> leave disconnected initially
```

Add to `/boot/firmware/config.txt`:

```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=17,i2c_gpio_scl=26
```

After reboot:

```bash
ls /dev/i2c-*
sudo i2cdetect -y 1
sudo i2cdetect -y 3
```

Expected:

```
bus 1 -> 0x29 VL53L0X, 0x68 MPU-6050
bus 3 -> 0x29 TCS34725
```

The colour sensor is a short-range point sensor. It cannot search the board like a camera. It is only useful when the patient is close and actually within its small sensing area.

The camera should be the primary patient-alignment sensor. The colour sensor may provide close-range confirmation if its mounting allows it to see the patient.

### 4.5 Pi Camera

Connect the official Raspberry Pi Camera V2 to the Pi CSI connector.

Test it with:

```bash
rpicam-hello --list-cameras
rpicam-hello --timeout 0
```

Planned use:

- Camera inactive or ignored in the starting zone.

- IR detects the starting landmark.

- Pi transitions to active navigation.

- Camera detects the patient and estimates horizontal position.

- Negative signed error means patient is left.

- Positive signed error means patient is right.

- Pi turns until the patient is centred.

- ToF handles approximate approach distance.

---

## 5. Pi actuators

### 5.1 Five servos

| Mechanism | Servo | Signal pin | Power |
| --- | --- | --- | --- |
| Ramp | MG995 | physical 32 / GPIO12 | separate regulated 5 V |
| Sweeper | MG90S | physical 33 / GPIO13 | separate regulated 5 V |
| Trapdoor 1 | SG90 | physical 36 / GPIO16 | separate regulated 5 V |
| Trapdoor 2 | SG90 | physical 12 / GPIO18 | separate regulated 5 V |
| Medical-kit release | MG995 | physical 35 / GPIO19 | separate regulated 5 V |

All servo grounds must connect to the common ground. Do not power a servo from a Pi GPIO pin.

The two trapdoors are commanded together.

Servo angles remain calibration values:

```python
ramp_up
ramp_down
sweeper_home
sweeper_in
trapdoor_closed
trapdoor_open
kit_closed
kit_open
```

Do not command live servos until mechanical limits have been checked by hand.

### 5.2 28BYJ-48 drum stepper and ULN2003

| ULN2003 input | Pi physical pin | Pi BCM GPIO |
| --- | --- | --- |
| IN1 | 7 | GPIO4 |
| IN2 | 29 | GPIO5 |
| IN3 | 31 | GPIO6 |
| IN4 | 38 | GPIO20 |
| VCC | separate regulated 5 V | — |
| GND | common GND | — |
| Motor socket | 28BYJ-48 plug | — |

The ULN2003 board normally does not use a TB6612-style `STBY` pin. It uses four input signals.

Drum slots:

```
Slot 1 = Y1
Slot 2 = red
Slot 3 = Y2
Slot 4 = green
```

The drum starts physically at slot 1/Y1. The intended software movement is:

```python
delta = (target_slot - current_slot) % 4
```

Required measurement:

```
steps per drum slot
coil sequence/direction
whether the drum must be de-energised after movement
```

---

## 6. ESP32 proposed GPIO map

> These are the proposed assignments from the current firmware. The actual Arduino/PCB wiring must take priority. Confirm the bottom wiring comments from the team before soldering.

### 6.1 Pi UART connection

| Signal | ESP32 GPIO | Pi connection |
| --- | --- | --- |
| RX2 | GPIO16 | Pi physical pin 8 / GPIO14 TX |
| TX2 | GPIO17 | Pi physical pin 10 / GPIO15 RX |
| GND | GND | Pi physical pin 6 |

UART is crossed:

```
Pi TX -> ESP32 RX GPIO16
Pi RX -> ESP32 TX GPIO17
Pi GND -> ESP32 GND
```

Use:

```
115200 baud, 8 data bits, no parity, 1 stop bit
```

### 6.2 TB6612FNG board 1

| TB6612 signal | ESP32 GPIO |
| --- | --- |
| PWMA / Motor 1 PWM | GPIO13 |
| AIN1 / Motor 1 direction | GPIO14 |
| AIN2 / Motor 1 direction | GPIO18 |
| PWMB / Motor 2 PWM | GPIO19 |
| BIN1 / Motor 2 direction | GPIO21 |
| BIN2 / Motor 2 direction | GPIO22 |
| STBY | GPIO27 |

Motor screw terminals:

```
A01 + A02 -> Motor 1 two motor wires
B01 + B02 -> Motor 2 two motor wires
```

### 6.3 TB6612FNG board 2

| TB6612 signal | ESP32 GPIO |
| --- | --- |
| PWMA / Motor 3 PWM | GPIO23 |
| AIN1 / Motor 3 direction | GPIO12 |
| AIN2 / Motor 3 direction | GPIO15 |
| PWMB / Motor 4 PWM | GPIO5 |
| BIN1 / Motor 4 direction | GPIO2 |
| BIN2 / Motor 4 direction | GPIO4 |
| STBY | GPIO27 |

Motor screw terminals:

```
A01 + A02 -> Motor 3 two motor wires
B01 + B02 -> Motor 4 two motor wires
```

One motor must use one complete output pair. Do not split one motor across channels.

Both TB6612 boards are assumed to share `STBY` on GPIO27. If the PCB already ties `STBY` to a logic rail, the firmware must be changed accordingly.

### 6.4 Encoder connections

| Motor | Encoder A | Encoder B |
| --- | --- | --- |
| Motor 1 | ESP32 GPIO34 | ESP32 GPIO35 |
| Motor 2 | ESP32 GPIO36 | ESP32 GPIO39 |
| Motor 3 | ESP32 GPIO32 | ESP32 GPIO33 |
| Motor 4 | ESP32 GPIO25 | ESP32 GPIO26 |

For every encoder:

```
Encoder VCC -> confirmed encoder supply
Encoder GND -> common ground
Encoder A   -> assigned A GPIO
Encoder B   -> assigned B GPIO
```

GPIO34, GPIO35, GPIO36, and GPIO39 are input-only and do not have normal internal pull-ups. Encoder outputs must be 3.3 V safe and must have suitable external pull-ups if required.

---

## 7. Power distribution

The battery is a 12.8 V LiFePO4 4S1P pack.

The battery must not be connected directly to:

```
Raspberry Pi GPIO
ESP32 3.3 V pin
sensors
servos
ULN2003 VCC
```

Required regulated rails:

```
12.8 V battery
    -> regulator for Raspberry Pi input
    -> regulator for servo 5 V rail
    -> regulator for stepper 5 V rail
    -> appropriate motor rail for TB6612 VM
    -> regulated logic rail as required
```

Required common ground:

```
Pi GND
ESP32 GND
TB6612 GND
encoder GND
sensor GND
servo supply GND
stepper supply GND
```

The motor supply must connect to the TB6612 motor-voltage input, not the ESP32 3.3 V rail.

Measure each rail with a multimeter before connecting loads:

```
3.3 V sensor rail -> approximately 3.3 V
5 V servo rail   -> approximately 5 V
5 V stepper rail -> approximately 5 V
motor rail       -> appropriate voltage for N20 motors
```

A physical emergency stop should remove motor/actuator power. A software stop is not a substitute for a physical emergency stop.

---

## 8. Pi-to-ESP32 command protocol

The Pi performs all navigation calculations and sends a complete action.

### Command format

```
<V,sequence,direction,speed,duration_ms,distance_mm,checksum>\n
```

The checksum is an XOR of every character in the body before the final checksum field.

Example body:

```
V,1,F,0.30,1500,420
```

The final packet is:

```
<V,1,F,0.30,1500,420,XX>
```

where `XX` is calculated by the Pi.

### Directions

```
F = forward
B = backward
L = in-place left turn
R = in-place right turn
S = stop
```

### Meaning of fields

| Field | Meaning |
| --- | --- |
| `V` | velocity/action packet |
| `sequence` | packet number |
| `direction` | F/B/L/R/S |
| `speed` | normalized motor command, 0.0 to 1.0 |
| `duration_ms` | exact run time calculated by Pi |
| `distance_mm` | Pi’s planned distance; ESP32 echoes/accepts it but does not calculate with it |
| `checksum` | XOR validation field |

### Responses

Accepted:

```
<A,1,START,checksum>
```

Completed:

```
<C,1,DONE,checksum>
```

Encoder report:

```
<E,sequence,motor1_count,motor2_count,motor3_count,motor4_count,checksum>
```

Fault examples:

```
<F,1,BAD_VALUE,checksum>
<F,1,BAD_DIRECTION,checksum>
<F,1,CHECKSUM,checksum>
```

The ESP32 must stop when it receives a stop command. A raw command timeout may also be used as a safety fallback.

---

## 9. How one movement works

Example: the Pi wants to move forward 420 mm.

1. Pi reads the route state.

1. Pi calculates the required speed and duration.

1. Pi sends a packet such as:

   ```
   V,1,F,0.30,1500,420
   ```

1. ESP32 verifies the checksum.

1. ESP32 maps `F` to:

   ```
   left motors = forward
   right motors = forward
   ```

1. ESP32 applies PWM corresponding to `0.30`.

1. ESP32 runs for 1500 ms.

1. ESP32 stops all motors.

1. ESP32 sends `DONE`.

1. ESP32 continues sending encoder counts.

1. Pi uses returned encoder counts for logging, calibration, and later control decisions.

For a right turn:

```
V,2,R,0.25,700,0
```

The ESP32 maps this to:

```
left motors = forward
right motors = reverse
```

The Pi remains responsible for deciding that 700 ms is the correct turn duration.

---

## 10. Robot operating sequence

The final state machine should follow the confirmed competition route rather than inventing distances.

General sequence:

1. Place the drum physically at Y1/slot 1.

1. Ensure ramp, sweeper, trapdoors, and kit release are in safe starting positions.

1. Start the Pi program headlessly.

1. Pi commands the robot forward.

1. IR S2/S3/S4 detect the starting black landmark.

1. Pi stops or changes state after confirming the landmark.

1. Camera-guided patient alignment becomes active.

1. Camera centres the patient horizontally.

1. ToF confirms approximate close distance.

1. Ramp lifts.

1. Sweeper moves inward.

1. Patient enters the mechanism.

1. Patient colour is confirmed if the colour sensor can see it.

1. Pi chooses the correct drum slot.

1. Drum rotates using the measured slot step count.

1. Process repeats for the remaining patients.

1. IR/ToF landmarks cause route transitions.

1. Trapdoors release the appropriate patient groups.

1. Medical-kit servo releases the required kits.

1. Pi returns the robot and finishes in a stopped state.

The exact route transitions, turning directions, and measured distances remain calibration work.

---

## 11. Testing order

### Sensor-only test

Use:

```bash
python3 patient_sensor_test.py --wizard
```

The wizard tests one item at a time:

1. I2C scan.

1. MPU-6050.

1. VL53L0X.

1. TCS34725.

1. IR array.

1. Pi camera.

Press Enter for the next test or type `q` to stop.

### Expected I2C result

Bus 1:

```
0x29 = VL53L0X
0x68 = MPU-6050
```

Bus 3:

```
0x29 = TCS34725
```

### ESP32 bench test

1. Upload the ESP32 firmware with motor power disconnected.

1. Power the ESP32 from USB.

1. Confirm its startup message.

1. Check Pi-to-ESP32 UART wiring.

1. Send `PING` and confirm `PONG`.

1. Send a stop command.

1. Lift the wheels off the floor.

1. Connect one TB6612 channel.

1. Test low-speed forward.

1. Test low-speed reverse.

1. Confirm the correct motor turns.

1. Add the remaining motors one at a time.

1. Add encoders after motor direction works.

1. Confirm encoder counts change in the expected direction.

### Stepper test

1. Keep the drum unloaded.

1. Test one direction.

1. Test the reverse direction.

1. Count steps for one exact compartment.

1. Test a full four-slot rotation.

1. Confirm the drum does not jam.

1. Confirm coils are released after movement if required.

### Servo test

1. Connect only the signal wire first.

1. Confirm the separate 5 V supply.

1. Move one servo at a time.

1. Start near the centre of its safe range.

1. Stop before mechanical binding.

1. Record safe angles.

1. Test the two trapdoors together.

---

## 12. Calibration values still required

Fill these only after physical measurement:

```python
TOF_CLOSE_MM
WHEEL_DIAMETER_MM
ENCODER_COUNTS_PER_MM
STEPPER_STEPS_PER_SLOT
```

Servo values:

```python
ramp_up
ramp_down
sweeper_home
sweeper_in
trapdoor_closed
trapdoor_open
kit_closed
kit_open
```

Also measure/confirm:

- Motor polarity.

- Encoder A/B polarity.

- Encoder counts per revolution.

- Actual wheel diameter under load.

- Wheel spacing.

- Motor speed versus PWM.

- Duration required for common route movements.

- ToF reading at the pickup distance.

- IR active polarity and landmark behaviour.

- TCS colour readings for real red, yellow, green, white, and black surfaces.

- Camera target-centering tolerance.

---

## 13. Current unresolved hardware confirmations

Before final autonomous operation, confirm:

- Actual ESP32/PCB GPIO assignments from the Arduino wiring comments.

- Which motor is Motor 1, 2, 3, and 4.

- Whether Motors 1/2 are the left side and Motors 3/4 are the right side.

- Whether both TB6612 `STBY` pins are connected to GPIO27 or tied to 3.3 V.

- TB6612 logic voltage and motor supply voltage.

- Encoder output voltage compatibility with ESP32 inputs.

- Encoder A/B pin order.

- External encoder pull-ups.

- Physical emergency-stop arrangement.

- Servo regulator current capacity.

- Motor regulator current capacity.

- Exact route timings/distances.

- Final camera patient-detection method.

- Final TCS34725 role and mounting position.

> Do not treat the proposed ESP32 GPIO table as confirmed until it matches the actual PCB/Arduino wiring block.

---

## 14. Software files

| File | Purpose |
| --- | --- |
| `patient_pi_master.py` | Pi master state machine, sensors, servos, stepper, UART |
| `patient_sensor_test.py` | Read-only interactive sensor tester |
| `esp32_uart_motor_executor.ino` | ESP32 UART parser and timed motor executor |
| `final_full_gpio_layout.md` | Pi-focused wiring reference |
| `galileo_disk_detector_hardened.py` | Separate wall/disk robot vision module; not used by this robot |

The ESP32 firmware should be updated only after the actual motor/encoder GPIO mapping is confirmed.
