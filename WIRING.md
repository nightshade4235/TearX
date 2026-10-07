# Robot M — Revised Raspberry Pi 4 + ESP32-S3 Wiring Guide

**Revision:** 07 October 2026
**Controller:** Raspberry Pi 4 master + ESP32-S3-DevKitC-1 motor/encoder slave
**Motor drivers:** Two L298N modules
**Reference:** `robot-m-schematic.pdf`, Rev A, 06 October 2026

> The Raspberry Pi sensor, servo, and stepper wiring remains the previous arrangement. The ESP32 motor side is changed to the new schematic: two L298N boards, shared left/right PWM and direction signals, and eight separate encoder signals.

---

## 1. System responsibilities

### Raspberry Pi 4

The Pi manages:

- IR array.

- VL53L0X ToF.

- MPU-6050.

- TCS34725/CJMCU-34725 on separate software I2C.

- Camera.

- Navigation and route decisions.

- Camera patient alignment.

- Servo mechanisms.

- 28BYJ-48 drum stepper through ULN2003.

- UART commands to the ESP32-S3.

- Encoder data received from the ESP32-S3.

### ESP32-S3

The ESP32-S3 manages:

- UART packet reception and checksum validation.

- L298N input signals.

- Four motor outputs through two L298N boards.

- Eight encoder input signals.

- Timed motor execution requested by the Pi.

- Encoder report packets back to the Pi.

The ESP32-S3 does not choose the route or calculate navigation distance. The Pi supplies direction, speed, duration, and planned distance.

---

## 2. Raspberry Pi 4 GPIO table

Pi software uses **BCM GPIO numbers**. Wiring uses **physical pin numbers**.

| Pi function | BCM GPIO | Physical pin | Connection |
| --- | --- | --- | --- |
| Hardware I2C SDA | GPIO2 | 3 | VL53L0X + MPU-6050 SDA |
| Hardware I2C SCL | GPIO3 | 5 | VL53L0X + MPU-6050 SCL |
| UART TX | GPIO14 | 8 | ESP32-S3 UART RX |
| UART RX | GPIO15 | 10 | ESP32-S3 UART TX |
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
| Reserved/spare | GPIO21 | 40 | Leave unused |

### Pi power and ground

```
Physical pin 1  -> 3.3 V sensor rail
Physical pin 6  -> common GND
Physical pin 17 -> optional additional 3.3 V
Physical pin 26 -> optional additional GND
```

---

## 3. Raspberry Pi sensor wiring

### IR array

Use only one IR array and only S2/S3/S4:

| IR signal | Pi physical pin | Pi BCM |
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

### VL53L0X on hardware I2C bus 1

```
VIN/VCC -> Pi pin 1 / 3.3 V
GND     -> Pi pin 6 / GND
SDA     -> Pi pin 3 / GPIO2
SCL     -> Pi pin 5 / GPIO3
```

Expected address:

```
0x29 on bus 1
```

Only one VL53L0X should be connected because the modules share address `0x29` and no confirmed XSHUT wiring is available.

### MPU-6050 on hardware I2C bus 1

```
VCC -> Pi pin 1 / 3.3 V
GND -> Pi pin 6 / GND
SDA -> Pi pin 3 / GPIO2
SCL -> Pi pin 5 / GPIO3
AD0 -> GND for address 0x68
```

Expected address:

```
0x68 on bus 1
```

### TCS34725/CJMCU-34725 on software I2C bus 3

```
VCC -> Pi pin 1 / 3.3 V
GND -> Pi pin 6 / GND
SDA -> Pi pin 11 / GPIO17
SCL -> Pi pin 37 / GPIO26
INT -> disconnected
LED -> disconnected initially
```

Add to `/boot/firmware/config.txt`:

```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=17,i2c_gpio_scl=26
```

Expected:

```
bus 3 -> 0x29
```

The colour sensor is a short-range point sensor. The camera should be used for patient position/orientation; the colour sensor can read the patient after it rolls onto the ramp-mounted sensor.

---

## 4. Raspberry Pi actuators

### Five servos

| Mechanism | Servo | Pi signal | Power |
| --- | --- | --- | --- |
| Ramp | MG995 | pin 32 / GPIO12 | separate regulated 5 V |
| Sweeper | MG90S | pin 33 / GPIO13 | separate regulated 5 V |
| Trapdoor 1 | SG90 | pin 36 / GPIO16 | separate regulated 5 V |
| Trapdoor 2 | SG90 | pin 12 / GPIO18 | separate regulated 5 V |
| Medical-kit release | MG995 | pin 35 / GPIO19 | separate regulated 5 V |

```
Servo VCC -> separate regulated 5 V supply
Servo GND -> servo supply GND/common GND
Pi GND    -> same common GND
```

Never power servos from Pi GPIO pins.

### 28BYJ-48 and ULN2003

| ULN2003 signal | Pi physical pin | Pi BCM |
| --- | --- | --- |
| IN1 | 7 | GPIO4 |
| IN2 | 29 | GPIO5 |
| IN3 | 31 | GPIO6 |
| IN4 | 38 | GPIO20 |
| VCC | separate regulated 5 V | — |
| GND | common GND | — |

Drum mapping:

```
Slot 1 = Y1
Slot 2 = red
Slot 3 = Y2
Slot 4 = green
```

---

## 5. ESP32-S3 motor-controller map

The new schematic uses two L298N modules.

### Left L298N — U3

| ESP32-S3 GPIO | Net/function | L298N connection |
| --- | --- | --- |
| GPIO4 | L_PWM | ENA + ENB tied together |
| GPIO5 | L_DIR1 | IN1 + IN3 tied together |
| GPIO6 | L_DIR2 | IN2 + IN4 tied together |

Motor outputs:

```
OUT1 + OUT2 -> M1 left front
OUT3 + OUT4 -> M2 left rear
```

### Right L298N — U4

| ESP32-S3 GPIO | Net/function | L298N connection |
| --- | --- | --- |
| GPIO7 | R_PWM | ENA + ENB tied together |
| GPIO8 | R_DIR1 | IN1 + IN3 tied together |
| GPIO9 | R_DIR2 | IN2 + IN4 tied together |

Motor outputs:

```
OUT1 + OUT2 -> M3 right front
OUT3 + OUT4 -> M4 right rear
```

### Driver jumper requirements

The schematic specifies:

```
Remove 5V-EN jumper on both L298N modules.
Remove ENA jumper on both modules.
Remove ENB jumper on both modules.
```

The ESP32-S3 must provide PWM to the enable inputs.

### Motor polarity

The schematic labels each motor wire:

```
M1 red / M2 white
```

If a motor rotates in the wrong direction, power off before swapping its output pair or change the software inversion setting.

---

## 6. ESP32-S3 encoder wiring

Keep all encoder C1/C2 signals separate.

| Encoder | C1 signal | C2 signal |
| --- | --- | --- |
| Left front E1 | GPIO10 | GPIO11 |
| Left rear E2 | GPIO12 | GPIO13 |
| Right front E3 | GPIO14 | GPIO15 |
| Right rear E4 | GPIO16 | GPIO17 |

For every encoder connector:

```
VCC (black) -> +3V3_ENC
GND (blue)  -> common GND
C1 (green)  -> GPIO listed above
C2 (yellow) -> GPIO listed above
```

> Confirm the encoder output voltage. The ESP32-S3 GPIOs are not 5 V tolerant. If an encoder produces 5 V push-pull outputs, use a suitable level translator. If it is an open-collector output, use confirmed 3.3 V pull-ups.

The ESP32-S3 reports all eight counts to the Pi:

```
<E,sequence,LF_C1,LF_C2,LR_C1,LR_C2,RF_C1,RF_C2,RR_C1,RR_C2,checksum>
```

---

## 7. ESP32-S3 UART wiring

The schematic does not show UART pins. The current firmware uses these **proposed pins**:

| UART signal | ESP32-S3 | Raspberry Pi |
| --- | --- | --- |
| RX | GPIO18 | Pi TX, physical pin 8 / GPIO14 |
| TX | GPIO21 | Pi RX, physical pin 10 / GPIO15 |
| GND | GND | Pi GND, physical pin 6 |

Cross the signals:

```
Pi TX  -> ESP32-S3 GPIO18 RX
Pi RX  <- ESP32-S3 GPIO21 TX
Pi GND <-> ESP32-S3 GND
```

Use:

```
115200 baud, 8 data bits, no parity, 1 stop bit
```

Before wiring, confirm GPIO18 and GPIO21 are available on the actual ESP32-S3 board. If different UART pins are chosen, change these firmware macros:

```cpp
const int UART_RX_PIN = 18;
const int UART_TX_PIN = 21;
```

The Pi pins remain unchanged.

---

## 8. Power wiring

The schematic shows these rails:

```
+12V_MOTOR -> L298N motor supply
+5V_LOGIC  -> L298N logic supply and ESP32-S3 5V input
+3V3_ENC   -> encoder VCC
GND        -> common ground distribution point
```

Battery path:

```
12–14 V battery positive
    -> fuse close to battery
    -> main switch
    -> buck converter inputs
```

The schematic includes:

```
U1 buck -> +12V_MOTOR target
U2 buck -> regulated +5V_LOGIC
```

Confirm that the 12 V buck has sufficient input headroom. A 12.8 V battery may not provide enough headroom for a true regulated 12 V output as it discharges; a buck-boost converter may be required.

All grounds return to the common battery-negative distribution point:

```
Battery negative
Pi GND
ESP32-S3 GND
L298N U3 GND
L298N U4 GND
Encoder GND
Sensor GND
Servo supply GND
Stepper supply GND
```

Add/verify local capacitors:

```
470 uF near each L298N motor supply
100 uF near the logic supply
100 nF ceramic bypass at drivers and encoder supplies
```

The L298N can dissipate significant heat. Check driver temperature and motor voltage/current limits.

---

## 9. UART command responsibility

The Pi sends complete movement actions:

```
<V,sequence,direction,speed,duration_ms,distance_mm,checksum>
```

Directions:

```
F = forward
B = backward
L = left turn
R = right turn
S = stop
```

The Pi calculates the route, distance, speed, and duration. The ESP32-S3 translates the command into left/right L298N signals.

ESP32-S3 replies:

```
<A,sequence,START,checksum>
<C,sequence,DONE,checksum>
<E,sequence,LF_C1,LF_C2,LR_C1,LR_C2,RF_C1,RF_C2,RR_C1,RR_C2,checksum>
<F,sequence,reason,checksum>
```

---

## 10. Test order

1. Keep battery and motor power disconnected.

1. Check all rails for shorts.

1. Measure `+5V_LOGIC`.

1. Measure `+3V3_ENC`.

1. Confirm ESP32-S3 powers from the correct 5 V input.

1. Upload the ESP32-S3 firmware.

1. Confirm the USB debug message.

1. Confirm UART pin choice physically.

1. Connect Pi TX/RX crossed and common GND.

1. Test `PING`/`PONG`.

1. Connect one L298N logic supply.

1. Keep enable PWM low and test one motor with the wheel lifted.

1. Test forward and reverse.

1. Add the other motors one at a time.

1. Connect encoder VCC/GND only after voltage compatibility is confirmed.

1. Connect C1/C2 one motor at a time.

1. Confirm the encoder report changes.

1. Run the Pi sensor wizard separately:

```bash
python3 patient_sensor_test.py --wizard
```

1. Test the stepper unloaded.

1. Test servos one at a time.

1. Only then test an integrated movement.

---

## 11. Final unresolved confirmations

Before autonomous operation, confirm:

- ESP32-S3 UART RX/TX pins.

- Encoder output voltage.

- Whether encoder pull-ups are already present.

- L298N `5V-EN`, `ENA`, and `ENB` jumper removal.

- Motor polarity and physical motor order.

- Buck-converter output under load.

- L298N motor current and heat.

- Physical emergency stop.

- ToF and colour sensor response.

- Camera patient-detection method.

- Servo angles.

- Drum steps per slot.

- Exact route timings and distances.

The new wiring does **not** alter the Pi sensor/servo/stepper pin assignments. It replaces the old ESP32/TB6612 motor side with the ESP32-S3/L298N arrangement shown above.
