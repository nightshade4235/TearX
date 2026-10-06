/*
  CR8S patient robot - ESP32 UART motor executor

  The Raspberry Pi does ALL high-level work:
    - route and navigation
    - direction choice
    - distance calculation
    - turn-angle calculation
    - duration calculation
    - speed selection

  The ESP32 does ONLY:
    - validate/checksum UART packets
    - parse the Pi command
    - translate direction + speed into four motor outputs
    - run for the supplied duration
    - stop safely
    - return ACK/status and encoder counts

  UART2:
    ESP32 GPIO16 RX2 <- Pi physical pin 8 TX
    ESP32 GPIO17 TX2 -> Pi physical pin 10 RX
    ESP32 GND        -> Pi GND

  Packet format (checksum is XOR of the body):
    <V,sequence,direction,speed,duration_ms,distance_mm,checksum>\n
  direction:
    F = forward
    B = backward
    L = in-place left turn
    R = in-place right turn
    S = stop

  Examples before adding checksum:
    V,1,F,0.30,1500,420
    V,2,R,0.25,700,0
    V,3,S,0,0,0

  The distance_mm field is carried for logging/verification only. The ESP32
  does not calculate distance or decide when a route action is complete.
  duration_ms is the Pi's requested run time.
*/

#include <Arduino.h>
#include <math.h>

// ------------------------------ UART ---------------------------------------
HardwareSerial PiSerial(2);
static const long UART_BAUD = 115200;
static const int UART_RX = 16;
static const int UART_TX = 17;
String rxLine;

// ------------------------------ motors -------------------------------------
// TB6612 #1
static const int M1_PWM = 13;
static const int M1_IN1 = 14;
static const int M1_IN2 = 18;
static const int M2_PWM = 19;
static const int M2_IN1 = 21;
static const int M2_IN2 = 22;
// TB6612 #2
static const int M3_PWM = 23;
static const int M3_IN1 = 12;
static const int M3_IN2 = 15;
static const int M4_PWM = 5;
static const int M4_IN1 = 2;
static const int M4_IN2 = 4;
static const int STBY = 27;

// If a wheel moves opposite to the intended direction, change its value.
static const bool MOTOR_INVERTED[4] = {false, false, false, false};

// ----------------------------- encoders -----------------------------------
static const int ENC_A[4] = {34, 36, 32, 25};
static const int ENC_B[4] = {35, 39, 33, 26};
volatile long encoderCount[4] = {0, 0, 0, 0};
volatile uint8_t encoderLastA[4] = {0, 0, 0, 0};

static const unsigned long ENCODER_REPORT_MS = 100;
static const unsigned long MAX_COMMAND_MS = 30000;
unsigned long lastEncoderReport = 0;
unsigned long commandStopAt = 0;
long activeSequence = 0;
bool commandActive = false;

void IRAM_ATTR encoder1ISR() { uint8_t a=digitalRead(ENC_A[0]); if(a!=encoderLastA[0]){encoderCount[0]+=(a==digitalRead(ENC_B[0]))?1:-1;encoderLastA[0]=a;} }
void IRAM_ATTR encoder2ISR() { uint8_t a=digitalRead(ENC_A[1]); if(a!=encoderLastA[1]){encoderCount[1]+=(a==digitalRead(ENC_B[1]))?1:-1;encoderLastA[1]=a;} }
void IRAM_ATTR encoder3ISR() { uint8_t a=digitalRead(ENC_A[2]); if(a!=encoderLastA[2]){encoderCount[2]+=(a==digitalRead(ENC_B[2]))?1:-1;encoderLastA[2]=a;} }
void IRAM_ATTR encoder4ISR() { uint8_t a=digitalRead(ENC_A[3]); if(a!=encoderLastA[3]){encoderCount[3]+=(a==digitalRead(ENC_B[3]))?1:-1;encoderLastA[3]=a;} }

uint8_t xorChecksum(const String &body) {
  uint8_t result = 0;
  for (size_t i=0; i<body.length(); ++i) result ^= (uint8_t)body[i];
  return result;
}

String checksumText(const String &body) {
  char output[3];
  snprintf(output, sizeof(output), "%02X", xorChecksum(body));
  return String(output);
}

void sendFrame(const String &body) {
  PiSerial.print('<');
  PiSerial.print(body);
  PiSerial.print(',');
  PiSerial.print(checksumText(body));
  PiSerial.print(">\n");
}

void sendAck(long sequence, const String &status) {
  sendFrame(String("A,") + sequence + "," + status);
}

bool decodeFrame(const String &line, String &body) {
  if (line.length() < 6 || line[0] != '<' || line[line.length()-1] != '>') return false;
  String inside = line.substring(1, line.length()-1);
  int comma = inside.lastIndexOf(',');
  if (comma < 1) return false;
  body = inside.substring(0, comma);
  String supplied = inside.substring(comma+1);
  supplied.toUpperCase();
  return supplied == checksumText(body);
}

int splitFields(const String &body, String fields[], int limit) {
  int count=0, start=0;
  while (count < limit) {
    int comma=body.indexOf(',', start);
    if (comma < 0) { fields[count++]=body.substring(start); break; }
    fields[count++]=body.substring(start, comma);
    start=comma+1;
  }
  return count;
}

void motorOutput(int index, float command) {
  const int pwmPins[4] = {M1_PWM, M2_PWM, M3_PWM, M4_PWM};
  const int in1Pins[4] = {M1_IN1, M2_IN1, M3_IN1, M4_IN1};
  const int in2Pins[4] = {M1_IN2, M2_IN2, M3_IN2, M4_IN2};

  if (MOTOR_INVERTED[index]) command = -command;
  command = constrain(command, -1.0f, 1.0f);
  int duty = (int)(fabs(command) * 255.0f);

  if (command > 0.02f) {
    digitalWrite(in1Pins[index], HIGH);
    digitalWrite(in2Pins[index], LOW);
  } else if (command < -0.02f) {
    digitalWrite(in1Pins[index], LOW);
    digitalWrite(in2Pins[index], HIGH);
  } else {
    digitalWrite(in1Pins[index], LOW);
    digitalWrite(in2Pins[index], LOW);
    duty = 0;
  }
  analogWrite(pwmPins[index], duty);
}

void allMotors(float m1, float m2, float m3, float m4) {
  digitalWrite(STBY, HIGH);
  motorOutput(0, m1);
  motorOutput(1, m2);
  motorOutput(2, m3);
  motorOutput(3, m4);
}

void stopMotors() {
  motorOutput(0, 0);
  motorOutput(1, 0);
  motorOutput(2, 0);
  motorOutput(3, 0);
  digitalWrite(STBY, LOW);
  commandActive = false;
}

void executeVelocityCommand(long sequence, char direction, float speed, unsigned long durationMs, long distanceMm) {
  if (speed < 0.0f || speed > 1.0f || durationMs > MAX_COMMAND_MS) {
    sendFrame(String("F,") + sequence + ",BAD_VALUE");
    return;
  }

  activeSequence = sequence;
  if (direction == 'S' || speed == 0.0f || durationMs == 0) {
    stopMotors();
    sendAck(sequence, "STOP");
    return;
  }

  // Motor order is assumed to be: M1/M2 left side, M3/M4 right side.
  float left = 0.0f;
  float right = 0.0f;
  if (direction == 'F') { left = speed; right = speed; }
  else if (direction == 'B') { left = -speed; right = -speed; }
  else if (direction == 'L') { left = -speed; right = speed; }
  else if (direction == 'R') { left = speed; right = -speed; }
  else {
    sendFrame(String("F,") + sequence + ",BAD_DIRECTION");
    return;
  }

  allMotors(left, left, right, right);
  commandStopAt = millis() + durationMs;
  commandActive = true;
  // distanceMm is deliberately not used for control: Pi already planned it.
  (void)distanceMm;
  sendAck(sequence, "START");
}

void processBody(const String &body) {
  String f[8];
  int n=splitFields(body, f, 8);
  if (n < 1) return;

  if (f[0] == "P" && n == 2 && f[1] == "PING") {
    sendAck(0, "PONG");
    return;
  }
  if (f[0] == "S") {
    long seq=(n > 1) ? f[1].toInt() : 0;
    stopMotors();
    sendAck(seq, "STOP");
    return;
  }
  if (f[0] == "V" && n == 6) {
    long seq=f[1].toInt();
    char direction=f[2].length() ? f[2][0] : '?';
    float speed=f[3].toFloat();
    unsigned long duration=f[4].toInt();
    long distance=f[5].toInt();
    executeVelocityCommand(seq, direction, speed, duration, distance);
    return;
  }
  sendFrame("F,0,BAD_FRAME");
}

void readUart() {
  while (PiSerial.available()) {
    char c=(char)PiSerial.read();
    if (c == '\n') {
      String body;
      if (decodeFrame(rxLine, body)) processBody(body);
      else if (rxLine.length()) sendFrame("F,0,CHECKSUM");
      rxLine="";
    } else if (c != '\r') {
      if (rxLine.length() < 180) rxLine += c;
      else rxLine="";
    }
  }
}

void sendEncoderReport() {
  long c[4];
  noInterrupts();
  for (int i=0; i<4; ++i) c[i]=encoderCount[i];
  interrupts();
  static long reportSequence=0;
  sendFrame(String("E,") + (++reportSequence) + "," + c[0] + "," + c[1] + "," + c[2] + "," + c[3]);
}

void setup() {
  Serial.begin(115200);
  PiSerial.begin(UART_BAUD, SERIAL_8N1, UART_RX, UART_TX);

  const int pwmPins[4]={M1_PWM,M2_PWM,M3_PWM,M4_PWM};
  const int in1Pins[4]={M1_IN1,M2_IN1,M3_IN1,M4_IN1};
  const int in2Pins[4]={M1_IN2,M2_IN2,M3_IN2,M4_IN2};
  for (int i=0; i<4; ++i) {
    pinMode(pwmPins[i], OUTPUT);
    pinMode(in1Pins[i], OUTPUT);
    pinMode(in2Pins[i], OUTPUT);
    digitalWrite(in1Pins[i], LOW);
    digitalWrite(in2Pins[i], LOW);
    analogWrite(pwmPins[i], 0);
  }
  pinMode(STBY, OUTPUT);
  digitalWrite(STBY, LOW);

  for (int i=0; i<4; ++i) {
    pinMode(ENC_A[i], INPUT);
    pinMode(ENC_B[i], INPUT);
    encoderLastA[i]=digitalRead(ENC_A[i]);
  }
  attachInterrupt(digitalPinToInterrupt(ENC_A[0]), encoder1ISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[1]), encoder2ISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[2]), encoder3ISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[3]), encoder4ISR, CHANGE);

  stopMotors();
  Serial.println("ESP32 UART motor executor ready; motors disabled.");
}

void loop() {
  readUart();
  if (commandActive && (long)(millis() - commandStopAt) >= 0) {
    stopMotors();
    sendFrame(String("C,") + activeSequence + ",DONE");
  }
  if (millis() - lastEncoderReport >= ENCODER_REPORT_MS) {
    lastEncoderReport=millis();
    sendEncoderReport();
  }
}
