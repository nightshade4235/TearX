/*
  CR8S patient robot - Arduino Uno UART motor executor

  This is an emergency Uno-compatible version of the ESP32 executor.

  The Raspberry Pi still does ALL navigation, distance calculation, turn
  calculation, speed selection, and duration calculation.

  The Uno only:
    - receives Pi UART packets
    - validates checksums
    - maps F/B/L/R into four motor outputs
    - runs for the Pi-provided duration
    - stops safely
    - counts ONE encoder channel per motor
    - returns encoder counts over UART

  IMPORTANT UNO LIMITATION:
    A standard Uno does not have enough pins for four motors, eight full
    quadrature encoder signals, STBY, and UART at the same time. This sketch
    uses encoder channel A only. Encoder channel B is not connected to the
    Uno. The sign of the count is assigned from the commanded motor direction.
    This is less accurate than full quadrature and may miss pulses at speed.

  UART:
    Uno hardware RX pin 0 <- Pi TX, 3.3 V is safe as a HIGH input.
    Uno hardware TX pin 1 -> Pi RX through a 5 V-to-3.3 V divider/level shifter.
    Uno GND -> Pi GND.

  Disconnect Pi UART wires from pins 0/1 while uploading if the upload fails.

  Pi packet format:
    <V,sequence,direction,speed,duration_ms,distance_mm,checksum>\n
  Examples before adding checksum:
    V,1,F,0.30,1500,420
    V,2,R,0.25,700,0
    S,3
    P,PING
*/

#include <Arduino.h>

// ------------------------------ motor pins ---------------------------------
// Motor 1: TB6612 board 1 channel A
const uint8_t M1_PWM = 3;
const uint8_t M1_IN1 = 2;
const uint8_t M1_IN2 = 4;
// Motor 2: TB6612 board 1 channel B
const uint8_t M2_PWM = 5;
const uint8_t M2_IN1 = 7;
const uint8_t M2_IN2 = 8;
// Motor 3: TB6612 board 2 channel A
const uint8_t M3_PWM = 6;
const uint8_t M3_IN1 = 12;
const uint8_t M3_IN2 = 13;
// Motor 4: TB6612 board 2 channel B
const uint8_t M4_PWM = 9;
const uint8_t M4_IN1 = A0;
const uint8_t M4_IN2 = A1;

// Shared standby for both TB6612 boards.
const uint8_t TB_STBY = A2;

// One encoder channel per motor. Do not connect encoder B in this Uno mode.
const uint8_t ENC_A[4] = {A3, A4, A5, 10};

// Set true if a motor's physical forward direction is reversed.
const bool MOTOR_INVERTED[4] = {false, false, false, false};

const uint8_t PWM_PIN[4] = {M1_PWM, M2_PWM, M3_PWM, M4_PWM};
const uint8_t IN1_PIN[4] = {M1_IN1, M2_IN1, M3_IN1, M4_IN1};
const uint8_t IN2_PIN[4] = {M1_IN2, M2_IN2, M3_IN2, M4_IN2};

// ------------------------------- state -------------------------------------
volatile long encoderCount[4] = {0, 0, 0, 0};
bool encoderLast[4] = {false, false, false, false};
float currentMotorCommand[4] = {0, 0, 0, 0};

bool commandActive = false;
unsigned long stopAt = 0;
long activeSequence = 0;
unsigned long lastEncoderReport = 0;
const unsigned long ENCODER_REPORT_PERIOD_MS = 100;
const unsigned long MAX_COMMAND_MS = 30000UL;

String rxLine;

uint8_t xorChecksum(const String &body) {
  uint8_t result = 0;
  for (unsigned int i = 0; i < body.length(); ++i) {
    result ^= (uint8_t)body[i];
  }
  return result;
}

String checksumText(const String &body) {
  char output[3];
  snprintf(output, sizeof(output), "%02X", xorChecksum(body));
  return String(output);
}

void sendFrame(const String &body) {
  Serial.print('<');
  Serial.print(body);
  Serial.print(',');
  Serial.print(checksumText(body));
  Serial.print(">\n");
}

void sendAck(long sequence, const String &status) {
  sendFrame(String("A,") + sequence + "," + status);
}

bool decodeFrame(const String &line, String &body) {
  if (line.length() < 6 || line[0] != '<' || line[line.length() - 1] != '>') {
    return false;
  }
  String inside = line.substring(1, line.length() - 1);
  int comma = inside.lastIndexOf(',');
  if (comma < 1) return false;
  body = inside.substring(0, comma);
  String provided = inside.substring(comma + 1);
  provided.toUpperCase();
  return provided == checksumText(body);
}

int splitFields(const String &body, String fields[], int limit) {
  int count = 0;
  int start = 0;
  while (count < limit) {
    int comma = body.indexOf(',', start);
    if (comma < 0) {
      fields[count++] = body.substring(start);
      break;
    }
    fields[count++] = body.substring(start, comma);
    start = comma + 1;
  }
  return count;
}

void setMotor(uint8_t motor, float command) {
  if (MOTOR_INVERTED[motor]) command = -command;
  command = constrain(command, -1.0, 1.0);
  currentMotorCommand[motor] = command;

  int duty = (int)(abs(command) * 255.0);
  if (abs(command) < 0.02) duty = 0;

  if (command > 0.02) {
    digitalWrite(IN1_PIN[motor], HIGH);
    digitalWrite(IN2_PIN[motor], LOW);
  } else if (command < -0.02) {
    digitalWrite(IN1_PIN[motor], LOW);
    digitalWrite(IN2_PIN[motor], HIGH);
  } else {
    digitalWrite(IN1_PIN[motor], LOW);
    digitalWrite(IN2_PIN[motor], LOW);
    duty = 0;
  }
  analogWrite(PWM_PIN[motor], duty);
}

void applyMotors(float m1, float m2, float m3, float m4) {
  digitalWrite(TB_STBY, HIGH);
  setMotor(0, m1);
  setMotor(1, m2);
  setMotor(2, m3);
  setMotor(3, m4);
}

void stopMotors() {
  setMotor(0, 0);
  setMotor(1, 0);
  setMotor(2, 0);
  setMotor(3, 0);
  digitalWrite(TB_STBY, LOW);
  commandActive = false;
}

void pollEncoders() {
  // Polling is intentionally simple for Uno compatibility. It is not as
  // reliable as ESP32 interrupts/full quadrature at high motor speed.
  for (uint8_t i = 0; i < 4; ++i) {
    bool current = digitalRead(ENC_A[i]);
    if (current && !encoderLast[i]) {
      if (currentMotorCommand[i] >= 0) encoderCount[i]++;
      else encoderCount[i]--;
    }
    encoderLast[i] = current;
  }
}

void sendEncoderReport() {
  static long reportSequence = 0;
  noInterrupts();
  long c0 = encoderCount[0];
  long c1 = encoderCount[1];
  long c2 = encoderCount[2];
  long c3 = encoderCount[3];
  interrupts();
  sendFrame(String("E,") + (++reportSequence) + "," + c0 + "," + c1 + "," + c2 + "," + c3);
}

void executeCommand(long sequence, char direction, float speed,
                    unsigned long durationMs, long distanceMm) {
  if (speed < 0.0 || speed > 1.0 || durationMs > MAX_COMMAND_MS) {
    sendFrame(String("F,") + sequence + ",BAD_VALUE");
    return;
  }

  activeSequence = sequence;
  if (direction == 'S' || speed == 0.0 || durationMs == 0) {
    stopMotors();
    sendAck(sequence, "STOP");
    return;
  }

  float left = 0;
  float right = 0;
  if (direction == 'F') {
    left = speed;
    right = speed;
  } else if (direction == 'B') {
    left = -speed;
    right = -speed;
  } else if (direction == 'L') {
    left = -speed;
    right = speed;
  } else if (direction == 'R') {
    left = speed;
    right = -speed;
  } else {
    sendFrame(String("F,") + sequence + ",BAD_DIRECTION");
    return;
  }

  // Motor 1/2 are assumed left; Motor 3/4 are assumed right.
  applyMotors(left, left, right, right);
  stopAt = millis() + durationMs;
  commandActive = true;
  (void)distanceMm;  // distance is calculated by the Pi, not the Uno
  sendAck(sequence, "START");
}

void processBody(const String &body) {
  String fields[8];
  int count = splitFields(body, fields, 8);
  if (count < 1) return;

  if (fields[0] == "P" && count == 2 && fields[1] == "PING") {
    sendAck(0, "PONG");
    return;
  }

  if (fields[0] == "S") {
    long sequence = count > 1 ? fields[1].toInt() : 0;
    stopMotors();
    sendAck(sequence, "STOP");
    return;
  }

  if (fields[0] == "V" && count == 6) {
    long sequence = fields[1].toInt();
    char direction = fields[2].length() ? fields[2][0] : '?';
    float speed = fields[3].toFloat();
    unsigned long durationMs = (unsigned long)fields[4].toInt();
    long distanceMm = fields[5].toInt();
    executeCommand(sequence, direction, speed, durationMs, distanceMm);
    return;
  }

  sendFrame("F,0,BAD_FRAME");
}

void readUart() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      String body;
      if (decodeFrame(rxLine, body)) processBody(body);
      else if (rxLine.length()) sendFrame("F,0,CHECKSUM");
      rxLine = "";
    } else if (c != '\r') {
      if (rxLine.length() < 180) rxLine += c;
      else rxLine = "";
    }
  }
}

void setup() {
  Serial.begin(115200);

  for (uint8_t i = 0; i < 4; ++i) {
    pinMode(PWM_PIN[i], OUTPUT);
    pinMode(IN1_PIN[i], OUTPUT);
    pinMode(IN2_PIN[i], OUTPUT);
    digitalWrite(IN1_PIN[i], LOW);
    digitalWrite(IN2_PIN[i], LOW);
    analogWrite(PWM_PIN[i], 0);
    pinMode(ENC_A[i], INPUT);
    encoderLast[i] = digitalRead(ENC_A[i]);
  }

  pinMode(TB_STBY, OUTPUT);
  digitalWrite(TB_STBY, LOW);
  stopMotors();
  Serial.println("Arduino Uno UART motor executor ready; motors disabled.");
}

void loop() {
  readUart();
  pollEncoders();

  if (commandActive && (long)(millis() - stopAt) >= 0) {
    stopMotors();
    sendFrame(String("C,") + activeSequence + ",DONE");
  }

  if (millis() - lastEncoderReport >= ENCODER_REPORT_PERIOD_MS) {
    lastEncoderReport = millis();
    sendEncoderReport();
  }
}
