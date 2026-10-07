# Robot 2 — Pi 4, Servo HAT, Sensors, Power, UART, and ESP32-S3 Wiring

**Purpose:** disk/sample collection, quarantine-beam placement, and laboratory delivery.
**Motor controller:** unchanged ESP32-S3 + two L298N arrangement from `robot-m-schematic.pdf`.

> This guide keeps the ESP32 motor and encoder GPIO assignment unchanged. Robot 2 adds its own Pi-side sensors and nine Servo HAT channels.

## 1. System split

### Raspberry Pi 4

- Navigation state machine.

- Raspberry Pi camera and disk detector.

- One IR array using S2/S3/S4.

- One VL53L0X ToF sensor.

- Optional MPU-6050.

- Waveshare 16-channel Servo HAT.

- Nine servo mechanisms.

- UART commands to ESP32-S3.

- Encoder packets received from ESP32-S3.

### ESP32-S3 DevKitC-1

- Four motors through two L298N modules.

- Eight encoder signals: C1/C2 for each motor.

- UART command reception and encoder packet transmission.

- No route decisions and no servo control.

## 2. Pi GPIO and I2C

| Pi function | BCM GPIO | Physical pin | Connection |
| --- | --- | --- | --- |
| Hardware I2C SDA | GPIO2 | 3 | VL53L0X + MPU-6050 + Servo HAT SDA |
| Hardware I2C SCL | GPIO3 | 5 | VL53L0X + MPU-6050 + Servo HAT SCL |
| UART TX | GPIO14 | 8 | ESP32-S3 GPIO18 RX |
| UART RX | GPIO15 | 10 | ESP32-S3 GPIO21 TX |
| Common GND | — | 6 | ESP32, sensors, drivers, regulator grounds |
| IR S2 | GPIO27 | 13 | IR array S2 |
| IR S3 | GPIO22 | 15 | IR array S3 |
| IR S4 | GPIO23 | 16 | IR array S4 |

The Pi camera connects to the Pi CSI camera connector, not a GPIO pin.

## 3. IR array

Only use the tested signals:

```
IR VCC -> Pi 3.3 V, physical pin 1 or 17
IR GND -> common GND, physical pin 6
S2    -> GPIO27, physical pin 13
S3    -> GPIO22, physical pin 15
S4    -> GPIO23, physical pin 16
```

Leave S1, S5, CLP, and NEAR disconnected unless the team has separately verified them.

The current tested interpretation is:

```
1 = black
0 = not black
```

The navigation trigger is therefore:

```
S2 == 1 AND S3 == 1 AND S4 == 1
```

## 4. I2C devices

All three devices may share hardware I2C because their addresses differ:

| Device | Address | Pi connection |
| --- | --- | --- |
| VL53L0X | 0x29 | GPIO2/GPIO3 |
| MPU-6050 | 0x68 | GPIO2/GPIO3 |
| Waveshare Servo HAT | normally 0x40 | GPIO2/GPIO3 |

### VL53L0X

```
VIN/VCC -> 3.3 V unless the module documentation explicitly permits another input
GND     -> common GND
SDA     -> Pi physical pin 3 / GPIO2
SCL     -> Pi physical pin 5 / GPIO3
```

### MPU-6050 (if installed)

```
VCC -> 3.3 V
GND -> common GND
SDA -> GPIO2
SCL -> GPIO3
AD0 -> GND for address 0x68
```

### Servo HAT logic

```
HAT SDA -> Pi physical pin 3 / GPIO2
HAT SCL -> Pi physical pin 5 / GPIO3
HAT GND -> common GND
HAT VCC/logic -> Pi 3.3 V only if required by that HAT documentation
HAT V+ -> separate regulated servo supply
```

Do not feed heavy servo current through the Pi 5 V rail.

## 5. Servo HAT channels

Proposed channel assignment; verify during assembly:

| Mechanism | HAT channel(s) |
| --- | --- |
| Disk gripper 1 | 0 grab, 3 tilt |
| Disk gripper 2 | 1 grab, 4 tilt |
| Disk gripper 3 | 2 grab, 5 tilt |
| Wall grabber left | 6 |
| Wall grabber right | 7 |
| Wall mechanism raise/lower | 8 |

Servo power:

```
Servo supply +5 to +6 V -> HAT V+
Servo supply GND          -> HAT GND
Pi GND                    -> same common ground
Servo signal              -> HAT channel only
```

Nine servos require a regulator and wiring rated for their combined stall current. Do not test all nine simultaneously until the regulator voltage and current capacity are confirmed.

## 6. ESP32-S3 and L298N wiring — unchanged

### Left L298N

| ESP32-S3 GPIO | Function | L298N |
| --- | --- | --- |
| GPIO4 | left PWM | ENA + ENB tied |
| GPIO5 | left direction 1 | IN1 + IN3 tied |
| GPIO6 | left direction 2 | IN2 + IN4 tied |

### Right L298N

| ESP32-S3 GPIO | Function | L298N |
| --- | --- | --- |
| GPIO7 | right PWM | ENA + ENB tied |
| GPIO8 | right direction 1 | IN1 + IN3 tied |
| GPIO9 | right direction 2 | IN2 + IN4 tied |

Motor supplies:

```
+12V_MOTOR -> both L298N VS / motor-supply inputs
+5V_LOGIC  -> both L298N VSS / logic-supply inputs
GND        -> both L298N GND pins and common ground
```

Keep the L298N jumper configuration exactly as in the working schematic. Do not change the ESP32 GPIO assignment.

## 7. Encoder wiring — unchanged

Robot 2 has four two-output encoders:

| Encoder | C1 | C2 |
| --- | --- | --- |
| Left front | GPIO10 | GPIO11 |
| Left rear | GPIO12 | GPIO13 |
| Right front | GPIO14 | GPIO15 |
| Right rear | GPIO16 | GPIO17 |

```
Encoder VCC -> ESP32 3.3 V only if outputs are 3.3 V compatible
Encoder GND -> common GND
```

If an encoder output is 5 V push-pull, it needs level shifting before entering an ESP32 GPIO.

## 8. ESP32 UART

```
Pi TX, physical pin 8 / GPIO14 -> ESP32-S3 GPIO18 RX
Pi RX, physical pin 10 / GPIO15 <- ESP32-S3 GPIO21 TX
Pi GND, physical pin 6         <-> ESP32-S3 GND
```

UART settings:

```
115200 baud, 8 data bits, no parity, 1 stop bit
```

## 9. Power distribution

The schematic's generic buck converters can be the LM2596 and XL4016, provided their ratings are suitable and outputs are measured first.

```
12.8 V LiFePO4 battery
  -> switch / E-stop / protection
  -> +12V_MOTOR regulator or motor rail -> L298N VS
  -> +5V_LOGIC buck                   -> ESP32 5V and L298N VSS
  -> separate servo regulator         -> Servo HAT V+
  -> regulated Pi supply              -> Raspberry Pi 5 V input
```

All negative outputs and grounds must meet at a common ground distribution point:

```
battery negative
Pi GND
ESP32 GND
L298N GND
Servo supply GND
sensor GND
```

Never connect the 12.8 V battery directly to the Pi 5 V input, ESP32 5 V input, servo V+, or L298N VSS.

## 10. Software

Copy these files into one Pi directory:

```
robot2_pi_navigation.py
galileo_disk_pi_master.py
camera.json                 # optional calibrated camera matrix
```

Install dependencies on the Pi:

```bash
sudo apt install -y python3-opencv python3-numpy python3-serial
sudo pip3 install adafruit-blinka adafruit-circuitpython-vl53l0x adafruit-circuitpython-servokit gpiozero
```

The navigation program is started with:

```bash
python3 robot2_pi_navigation.py
```

Dry-run syntax test:

```bash
python3 robot2_pi_navigation.py --dry-run
```

## 11. Calibration placeholders

Before floor testing, fill these in `robot2_pi_navigation.py`:

```
TOF_CLOSE_MM
TOF_CORNER_MM
HALFWAY_REVERSE_MM
GRIPPER_OFFSET_MM
SERVO_ANGLES[...]
```

Because there are no contact switches, the `wall_contact_fallback()` routine is only a slow mechanical settling assumption. It cannot electronically prove that both walls are touching.
