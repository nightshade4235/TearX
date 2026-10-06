# Arduino Uno Motor-Controller Wiring

This wiring matches:

```
arduino_uno_uart_motor_executor.ino
```

The Raspberry Pi remains the master. The Arduino Uno only receives movement packets, drives the four motors, times the command, and sends encoder counts back to the Pi.

> **Important:** This Uno version uses one encoder channel per motor. Encoder B is not connected because a standard Uno does not have enough practical pins for four full A/B encoder pairs plus four motors, two TB6612 boards, STBY, and UART.

---

## 1. Arduino Uno to Raspberry Pi UART

| Arduino Uno | Raspberry Pi |
| --- | --- |
| D0 / RX | Pi TX, physical pin 8 / GPIO14 |
| D1 / TX | Pi RX, physical pin 10 / GPIO15 through a 5 V-to-3.3 V divider or level shifter |
| GND | Pi physical pin 6 / common GND |

UART settings:

```
115200 baud
8 data bits
no parity
1 stop bit
```

The wires cross:

```
Pi TX -> Uno RX/D0
Pi RX <- Uno TX/D1 through level shifter
GND   -> GND
```

Do not connect Uno 5 V TX directly to the Raspberry Pi RX pin.

Disconnect the Pi UART wires from Uno D0/D1 while uploading if the Arduino IDE cannot upload.

---

## 2. TB6612FNG board 1

### Control wiring

| TB6612FNG signal | Arduino Uno pin |
| --- | --- |
| PWMA | D3 |
| AIN1 | D2 |
| AIN2 | D4 |
| PWMB | D5 |
| BIN1 | D7 |
| BIN2 | D8 |
| STBY | A2 |
| VCC | confirmed logic supply |
| GND | common ground |
| VM/Vmotor | motor regulator output |

### Motor terminals

```
TB6612 board 1 A01 + A02 -> Motor 1 two motor wires
TB6612 board 1 B01 + B02 -> Motor 2 two motor wires
```

Do not split one motor across the A and B channels.

---

## 3. TB6612FNG board 2

### Control wiring

| TB6612FNG signal | Arduino Uno pin |
| --- | --- |
| PWMA | D6 |
| AIN1 | D12 |
| AIN2 | D13 |
| PWMB | D9 |
| BIN1 | A0 |
| BIN2 | A1 |
| STBY | A2 |
| VCC | confirmed logic supply |
| GND | common ground |
| VM/Vmotor | motor regulator output |

### Motor terminals

```
TB6612 board 2 A01 + A02 -> Motor 3 two motor wires
TB6612 board 2 B01 + B02 -> Motor 4 two motor wires
```

Both TB6612 `STBY` pins share Arduino Uno A2:

```
Uno A2 -> TB6612 #1 STBY
Uno A2 -> TB6612 #2 STBY
```

The code drives `STBY` LOW while stopped and HIGH while moving.

---

## 4. Encoder wiring

This Uno sketch uses only encoder channel A.

| Motor | Encoder A output | Arduino Uno pin | Encoder B |
| --- | --- | --- | --- |
| Motor 1 | A | A3 | Leave disconnected |
| Motor 2 | A | A4 | Leave disconnected |
| Motor 3 | A | A5 | Leave disconnected |
| Motor 4 | A | D10 | Leave disconnected |

For every encoder:

```
Encoder VCC -> confirmed encoder supply
Encoder GND -> common ground
Encoder A   -> assigned Uno input above
Encoder B   -> leave disconnected in this Uno version
```

The encoder outputs must be compatible with the Uno input voltage. If the encoder output is 3.3 V, it is normally read as HIGH by the Uno, but confirm the module’s electrical specification.

The Uno assigns positive or negative counts from the commanded motor direction. It does not measure direction from encoder B.

---

## 5. Complete Arduino pin summary

| Uno pin | Function |
| --- | --- |
| D0 | UART RX from Pi TX |
| D1 | UART TX to Pi RX through level shifter |
| D2 | TB6612 #1 AIN1 / Motor 1 direction |
| D3 | TB6612 #1 PWMA / Motor 1 PWM |
| D4 | TB6612 #1 AIN2 / Motor 1 direction |
| D5 | TB6612 #1 PWMB / Motor 2 PWM |
| D6 | TB6612 #2 PWMA / Motor 3 PWM |
| D7 | TB6612 #1 BIN1 / Motor 2 direction |
| D8 | TB6612 #1 BIN2 / Motor 2 direction |
| D9 | TB6612 #2 PWMB / Motor 4 PWM |
| D10 | Motor 4 encoder A |
| D11 | Unused |
| D12 | TB6612 #2 AIN1 / Motor 3 direction |
| D13 | TB6612 #2 AIN2 / Motor 3 direction |
| A0 | TB6612 #2 BIN1 / Motor 4 direction |
| A1 | TB6612 #2 BIN2 / Motor 4 direction |
| A2 | Shared TB6612 STBY |
| A3 | Motor 1 encoder A |
| A4 | Motor 2 encoder A |
| A5 | Motor 3 encoder A |

---

## 6. Power wiring

The Uno must not power the motors.

```
Motor regulator output -> TB6612 VM/Vmotor
Motor regulator GND    -> TB6612 GND
Uno GND                -> TB6612 GND
Pi GND                 -> common GND
Encoder GND            -> common GND
```

TB6612 logic:

```
TB6612 VCC -> confirmed logic supply
```

Do not guess the board’s VCC requirement; confirm the actual TB6612 breakout documentation.

Do not connect the 12.8 V LiFePO4 battery directly to:

```
Arduino Uno logic pins
Raspberry Pi pins
encoder outputs
TB6612 VCC logic input
```

The battery must feed suitable regulators first.

---

## 7. Motor direction test

Upload the Uno sketch with the wheels lifted from the ground.

Test one motor at a low speed. If a motor’s physical forward direction is reversed, change the matching value in the sketch:

```cpp
const bool MOTOR_INVERTED[4] = {
  false, false, false, false
};
```

For example, to reverse Motor 2:

```cpp
const bool MOTOR_INVERTED[4] = {
  false, true, false, false
};
```

Never reverse direction by swapping arbitrary control wires while power is applied.

---

## 8. UART packet responsibility

The Pi sends a complete planned action:

```
<V,sequence,direction,speed,duration_ms,distance_mm,checksum>
```

Examples:

```
V,1,F,0.30,1500,420
V,2,R,0.25,700,0
S,3
P,PING
```

The Uno interprets:

```
F = forward
B = backward
L = left turn
R = right turn
S = stop
```

The Pi calculates the distance and duration. The Uno does not calculate route distance.

The Uno returns:

```
<A,sequence,START,checksum>
<C,sequence,DONE,checksum>
<E,sequence,encoder1,encoder2,encoder3,encoder4,checksum>
```

---

## 9. Safe connection order

1. Leave battery and motor power disconnected.

1. Upload the Uno sketch using USB.

1. Confirm the startup message at 115200 baud.

1. Connect the Pi UART with the correct level shifter on Uno TX.

1. Test `PING` and confirm `PONG`.

1. Connect TB6612 logic VCC and GND.

1. Keep `STBY` low while checking wiring.

1. Connect one motor to one complete output pair.

1. Lift the wheels.

1. Connect regulated motor power.

1. Test one motor at low speed.

1. Test reverse.

1. Add the other motors one at a time.

1. Add encoder A wires.

1. Confirm encoder counts change.

1. Only then place the robot on the floor.
