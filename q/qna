# Robot M — Final Questions Checklist

Use this checklist with the hardware and software team. Answer the **red/critical** items first. A robot cannot safely run until the critical items have definite answers.

---

## A. Controller and schematic identity — critical

- [ ] Is the motor controller definitely an **ESP32-S3-DevKitC-1**?

- [ ] Is the attached schematic the final physical wiring, not only a proposal?

- [ ] Are the motor drivers definitely **two L298N modules**, not TB6612FNG boards?

- [ ] Is the schematic revision `REV A / 06 OCT 2026` the version being assembled?

- [ ] Are the ESP32-S3 GPIO numbers printed on the actual board labels and available?

- [ ] Are GPIO4–GPIO17 wired exactly as shown in the schematic?

- [ ] Are GPIO18 and GPIO21 physically available for UART?

- [ ] Has someone checked the schematic against the real jumper wires with a continuity tester?

---

## B. Raspberry Pi UART — critical

The Pi UART pins are already selected:

```
Pi physical pin 8  / GPIO14 TX
Pi physical pin 10 / GPIO15 RX
Pi physical pin 6  / GND
```

Answer:

- [ ] Which ESP32-S3 GPIO is **RX** from the Pi?

- [ ] Which ESP32-S3 GPIO is **TX** to the Pi?

- [ ] Is the actual connection crossed: Pi TX → ESP RX and Pi RX → ESP TX?

- [ ] Is Pi GND connected to ESP32-S3 GND?

- [ ] Is UART set to `115200, 8N1` on both sides?

- [ ] Is the Pi using `/dev/serial0`?

- [ ] Is the ESP32-S3 UART using GPIO18/GPIO21, or different pins?

- [ ] Can the Pi send a `PING` and receive `PONG`?

- [ ] Does the ESP32-S3 return an ACK for a movement command?

- [ ] Does the ESP32-S3 return `DONE` after the command duration?

- [ ] Does the Pi receive encoder reports without corrupted characters?

- [ ] Is any USB serial console competing with the UART pins?

Recommended test packet:

```
<P,PING,checksum>
```

---

## C. Motor-driver wiring — critical

### Left L298N

The schematic says:

```
GPIO4 -> left ENA + ENB / L_PWM
GPIO5 -> left IN1 + IN3 / L_DIR1
GPIO6 -> left IN2 + IN4 / L_DIR2
```

Answer:

- [ ] Is GPIO4 connected to both left ENA and ENB?

- [ ] Is GPIO5 connected to both left IN1 and IN3?

- [ ] Is GPIO6 connected to both left IN2 and IN4?

- [ ] Is left front connected to OUT1/OUT2?

- [ ] Is left rear connected to OUT3/OUT4?

- [ ] Are the `5V-EN` jumpers removed?

- [ ] Are both `ENA` and `ENB` jumpers removed?

- [ ] Is the left L298N logic supply connected to +5V_LOGIC?

- [ ] Is its motor supply connected to +12V_MOTOR?

- [ ] Is its GND connected to common GND?

### Right L298N

The schematic says:

```
GPIO7 -> right ENA + ENB / R_PWM
GPIO8 -> right IN1 + IN3 / R_DIR1
GPIO9 -> right IN2 + IN4 / R_DIR2
```

Answer:

- [ ] Is GPIO7 connected to both right ENA and ENB?

- [ ] Is GPIO8 connected to both right IN1 and IN3?

- [ ] Is GPIO9 connected to both right IN2 and IN4?

- [ ] Is right front connected to OUT1/OUT2?

- [ ] Is right rear connected to OUT3/OUT4?

- [ ] Are the `5V-EN` jumpers removed?

- [ ] Are both `ENA` and `ENB` jumpers removed?

- [ ] Is its logic supply +5V_LOGIC?

- [ ] Is its motor supply +12V_MOTOR?

- [ ] Is its GND common with the ESP32-S3 and Pi?

### Motor behaviour

- [ ] Does every motor spin when tested individually?

- [ ] Does every motor spin in both directions?

- [ ] Which output pair corresponds to each physical wheel?

- [ ] Are the left-front and left-rear motors mechanically oriented the same way?

- [ ] Are the right-front and right-rear motors mechanically mirrored?

- [ ] Does a Pi `F` command make all four wheels move forward?

- [ ] Does a Pi `B` command make all four wheels move backward?

- [ ] Does `L` turn the robot left?

- [ ] Does `R` turn the robot right?

- [ ] Which motors need software inversion?

- [ ] Is the L298N overheating?

- [ ] Is the L298N voltage drop acceptable for the N20 motors?

---

## D. Encoder wiring and feedback — critical

The schematic assigns:

```
Left front:  C1 GPIO10, C2 GPIO11
Left rear:   C1 GPIO12, C2 GPIO13
Right front: C1 GPIO14, C2 GPIO15
Right rear:  C1 GPIO16, C2 GPIO17
```

Answer:

- [ ] Are all eight C1/C2 signals separate?

- [ ] Is every encoder VCC connected to +3V3_ENC?

- [ ] Is every encoder GND connected to common GND?

- [ ] Are the encoder outputs actually 3.3 V safe?

- [ ] Are they 5 V push-pull outputs?

- [ ] If they are 5 V outputs, are level shifters installed?

- [ ] If they are open-collector outputs, are 3.3 V pull-ups installed?

- [ ] Are GPIO10–GPIO17 free from other connections?

- [ ] Does each encoder count change when its wheel turns?

- [ ] Does C1 change independently from C2?

- [ ] Does the count direction match forward/reverse motion?

- [ ] What is the encoder counts-per-revolution value?

- [ ] Is the count x1, x2, or x4 decoded?

- [ ] Is the current firmware counting transitions correctly for the chosen interpretation?

- [ ] Are encoder wires routed away from motor-current wires?

---

## E. Power and battery — critical

- [ ] Is the battery the Pro-Range 12.8 V LiFePO4 pack?

- [ ] What is the battery’s actual voltage when fully charged?

- [ ] Is there a fuse close to battery positive?

- [ ] What is the fuse rating?

- [ ] Does the main switch cut the battery positive line?

- [ ] Is +12V_MOTOR actually regulated under load?

- [ ] Can the buck converter regulate 12 V as the 12.8 V battery discharges?

- [ ] Is a buck-boost converter required instead?

- [ ] Is +5V_LOGIC measured under load?

- [ ] Is +3V3_ENC measured under load?

- [ ] Is the ESP32-S3 powered from the correct 5 V input/VIN pin?

- [ ] Is the Pi powered by an appropriate regulator or its approved USB-C supply?

- [ ] Is there a separate high-current 5 V servo regulator?

- [ ] Is there a separate 5 V stepper supply if needed?

- [ ] Can the servo regulator supply both MG995 servos during stall/startup?

- [ ] Can the motor regulator supply all four N20 motor stall currents?

- [ ] Are all grounds connected at a suitable common distribution point?

- [ ] Are polarity and connector labels checked with a multimeter?

- [ ] Are the capacitors installed with correct polarity?

- [ ] Are there 470 uF capacitors near the L298N motor supplies?

- [ ] Is there 100 uF on the logic rail?

- [ ] Are 100 nF bypass capacitors fitted where required?

---

## F. Emergency stop and safety — critical

- [ ] Is there a physical E-stop?

- [ ] Does it physically disconnect motor power?

- [ ] Does it disconnect servo/actuator power if required?

- [ ] Does it work without software?

- [ ] Has it been tested with the wheels lifted?

- [ ] Does releasing/resetting the E-stop leave the motors stopped?

- [ ] Is the battery disconnect accessible during the run?

- [ ] Are motor wires secured away from wheels and mechanisms?

- [ ] Are exposed battery terminals insulated?

- [ ] Can the robot be lifted without touching an exposed live terminal?

---

## G. Pi sensor wiring — critical for navigation

### IR array

- [ ] Is only one IR array installed?

- [ ] Is S2 connected to Pi GPIO27 / physical pin 13?

- [ ] Is S3 connected to Pi GPIO22 / physical pin 15?

- [ ] Is S4 connected to Pi GPIO23 / physical pin 16?

- [ ] Is the IR array powered from 3.3 V?

- [ ] Is the IR ground connected to Pi ground?

- [ ] Does `1` mean black on the real surface?

- [ ] Is S2 physically left, S3 centre, S4 right?

- [ ] Can the array distinguish the starting line from a patient dot?

- [ ] Can a 20 mm black patient dot activate all three sensors?

- [ ] How many consecutive readings confirm a line?

### VL53L0X

- [ ] Is only one VL53L0X connected to bus 1?

- [ ] Does it appear at 0x29 on bus 1?

- [ ] Is it connected to Pi pins 3/5, not the colour bus?

- [ ] What is its reading at the intended pickup distance?

- [ ] What is its reading at the wall distance?

- [ ] What is the practical minimum reading?

- [ ] Is the sensor facing forward?

- [ ] What is the offset between sensor face and robot front?

- [ ] What reading should mean “close enough to pickup”?

- [ ] Does it produce stable readings or require averaging?

### MPU-6050

- [ ] Does it appear at 0x68?

- [ ] Does it show nonzero acceleration when tilted?

- [ ] Does it show gyro changes when rotated?

- [ ] Which physical axis is forward?

- [ ] Which direction is positive yaw?

- [ ] Is the gyro bias measured while stationary?

- [ ] Is the IMU needed for turns or only optional?

### TCS34725/CJMCU-34725

- [ ] Is it on software I2C bus 3?

- [ ] Does `sudo i2cdetect -y 3` show 0x29?

- [ ] Is it powered from 3.3 V?

- [ ] Is it physically mounted on the ramp?

- [ ] Does the patient roll directly over/in front of its sensing window?

- [ ] How far above the sensor is the patient surface?

- [ ] Is there enough illumination at that position?

- [ ] Is the onboard LED present and working?

- [ ] What raw values are measured for red, yellow, green, white, and black?

- [ ] How many readings confirm a colour?

- [ ] What happens if it returns too_dark or unknown?

- [ ] Is the colour read before or after the patient enters the drum?

### Camera

- [ ] Does `rpicam-hello --list-cameras` detect the camera?

- [ ] Is the lens clean and focused?

- [ ] Is the camera mounted forward-facing?

- [ ] What counts as a patient: red, green, blue, or any saturated coloured object?

- [ ] What minimum target size is detectable?

- [ ] Does the camera activate after the starting line?

- [ ] Does it ignore the starting-zone markings?

- [ ] How is patient position represented: pixel error or angle?

- [ ] What horizontal error is considered centred?

- [ ] Does the robot rotate first, then move forward?

- [ ] What ToF value stops the approach?

- [ ] What happens if no patient is detected?

- [ ] What happens if several coloured objects are visible?

- [ ] Does the camera turn off or remain active during pickup?

---

## H. Pi mechanisms — critical before live operation

### Ramp MG995

- [ ] Is the ramp initially up or down?

- [ ] What angle lowers it?

- [ ] What angle raises it?

- [ ] Does it clear the patient and floor?

- [ ] Does it stall at either endpoint?

- [ ] Does the colour sensor remain aligned after ramp movement?

### Sweeper MG90S

- [ ] Is it initially home or extended?

- [ ] Does ramp movement happen before the sweeper?

- [ ] What angle sweeps the patient inward?

- [ ] What angle returns home?

- [ ] Can it jam against the patient?

### Trapdoors SG90 x2

- [ ] Do both trapdoors move together?

- [ ] Are they mechanically mirrored?

- [ ] Do they require different numerical angles?

- [ ] Which angle is closed?

- [ ] Which angle is open?

- [ ] Can they hold position long enough to release patients?

### Medical-kit MG995

- [ ] Does it release six kits without jamming?

- [ ] What is the closed angle?

- [ ] What is the open angle?

- [ ] Does it return closed after release?

- [ ] Does it interfere with the drum?

### Drum stepper

- [ ] Is the stepper definitely a 28BYJ-48?

- [ ] Is the driver definitely ULN2003?

- [ ] Is the motor powered from a regulated 5 V rail?

- [ ] What is the correct coil sequence?

- [ ] Which direction is forward slot movement?

- [ ] How many steps move one slot?

- [ ] Does the drum start physically at Y1/slot 1?

- [ ] Can the drum skip steps under load?

- [ ] Does it need to hold position?

- [ ] Can coils be released after movement?

- [ ] What happens if a compartment jams?

---

## I. Patient pickup order — must be decided

Confirm this exact sequence:

- [ ] Camera detects a red/green/blue patient.

- [ ] Pi estimates whether the patient is left or right of centre.

- [ ] Pi rotates until the patient is in front.

- [ ] Pi moves forward toward the patient.

- [ ] ToF determines close enough.

- [ ] Pi stops.

- [ ] Ramp lowers or raises — which first?

- [ ] Sweeper moves inward — before or after ramp movement?

- [ ] Patient rolls onto the ramp-mounted colour sensor.

- [ ] Colour sensor reads the patient.

- [ ] Pi confirms the colour using repeated readings.

- [ ] Pi maps red/green/yellow to the drum slot.

- [ ] Drum rotates to the correct compartment.

- [ ] Patient is moved into the drum.

- [ ] Ramp/sweeper return home.

- [ ] Robot resumes searching.

Also answer:

- [ ] What does the robot do if the camera sees a patient but ToF never becomes close?

- [ ] What does it do if the colour sensor returns unknown?

- [ ] Does it retry pickup?

- [ ] How many retries are allowed?

- [ ] How does it avoid collecting the same patient twice?

---

## J. Drum capacity and patient mapping

- [ ] Confirm the four physical compartments:

   ```
   Y1, red, Y2, green
   ```

- [ ] Does Y1 hold exactly two patients?

- [ ] Does Y2 hold exactly two patients?

- [ ] Do red and green hold the expected number?

- [ ] When exactly does the yellow assignment switch from Y1 to Y2?

- [ ] Does a yellow patient always alternate, or fill Y1 first then Y2?

- [ ] What happens if more than two yellow patients are collected?

- [ ] Are the six medical kits separate from the drum?

- [ ] When are the kits released?

- [ ] Which patients are released at each PCC?

---

## K. Navigation and route — critical

- [ ] What exact movement crosses the starting line?

- [ ] Which IR condition confirms leaving the starting zone?

- [ ] When does the camera become active?

- [ ] Where is the first patient search area?

- [ ] How does the robot search if the patient is not centred?

- [ ] How does it move from one patient dot to the next?

- [ ] What confirms the middle H landmark?

- [ ] What exact turn occurs at the middle landmark?

- [ ] What confirms a wall/edge: ToF only, colour white, or both?

- [ ] What is the exact right-PCC route?

- [ ] What is the exact left-PCC route?

- [ ] Where are the red patients released?

- [ ] Where are the yellow patients released?

- [ ] Where are the six kits released?

- [ ] Where are the green patients released?

- [ ] What confirms that the robot has returned home?

- [ ] What is the final stop condition?

- [ ] Are route timings or measured distances available?

- [ ] Are turns timed, encoder-based, or IMU-based?

- [ ] Does the robot need to reverse before every turn?

---

## L. Software and startup

- [ ] Does the Pi run `patient_sensor_test.py --wizard` successfully?

- [ ] Do all required Python modules install system-wide?

- [ ] Does bus 3 exist after reboot?

- [ ] Does the camera work from the same user that runs the service?

- [ ] Is `/dev/serial0` available?

- [ ] Is the Pi user in the required serial/GPIO groups?

- [ ] Does `patient_pi_master.py --dry-run` produce valid packets?

- [ ] Does the Pi live code send `V` and `S` packets matching the ESP32 firmware?

- [ ] Does the Pi parse the new eight-value `E` packet?

- [ ] Is the ESP32-S3 firmware compiled for the correct ESP32-S3 board?

- [ ] Are the UART pins in the firmware the physically wired pins?

- [ ] Does the systemd service start only after the hardware is ready?

- [ ] Does the service stop motors on shutdown?

- [ ] Does the service log UART, sensor, and fault errors?

- [ ] Is there a safe manual way to prevent startup movement while assembling?

---

## M. Calibration values to record

Write down the actual measured values:

```
ToF pickup threshold:                 ______ mm
ToF wall threshold:                   ______ mm
Wheel diameter:                       ______ mm
Wheel track/spacing:                  ______ mm
Encoder counts per revolution:        ______
Encoder counts per millimetre:        ______
Stepper steps per drum slot:          ______
Ramp up angle:                        ______ degrees
Ramp down angle:                      ______ degrees
Sweeper home angle:                   ______ degrees
Sweeper in angle:                     ______ degrees
Trapdoor closed angle:                ______ degrees
Trapdoor open angle:                  ______ degrees
Kit closed angle:                     ______ degrees
Kit open angle:                       ______ degrees
Forward speed:                        ______
Reverse speed:                        ______
90-degree turn duration:              ______ ms
180-degree turn duration:             ______ ms
Common route leg durations:            ______ ms
```

---

## N. Minimum answers needed to attempt a run today

If time is extremely limited, answer these first:

1. Which ESP32-S3 pins are UART RX/TX?

1. Is the common ground connected between Pi and ESP32-S3?

1. Are the two L298N drivers wired exactly to GPIO4–GPIO9?

1. Are all four motors mapped to the intended wheels?

1. Does one motor run forward and reverse?

1. Does the Pi receive an encoder packet?

1. Are encoder outputs 3.3 V safe?

1. Is +12V_MOTOR measured and safe?

1. Is +5V_LOGIC measured and safe?

1. Is +3V3_ENC measured and safe?

1. Is the physical E-stop present and tested?

1. Do the IR sensors respond correctly?

1. Does the ToF respond at the expected distance?

1. Does the camera detect a coloured patient?

1. What exact order is ramp, sweeper, colour reading, and drum movement?

1. What are the safe servo angles?

1. What are the stepper steps per slot?

1. What exact route action follows each landmark?

1. What does the robot do when a sensor fails?

1. Is the robot allowed to run in a simplified timed baseline if full camera/encoder control is not ready?
