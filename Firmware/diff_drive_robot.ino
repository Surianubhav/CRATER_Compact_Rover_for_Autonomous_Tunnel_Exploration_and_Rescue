/*
  ============================================================================
  2-WHEEL DIFFERENTIAL DRIVE ROBOT — FlySky FS-R6B + BTS7960 + Arduino Uno
  ============================================================================

  HARDWARE / WIRING (must match your build exactly):

  Receiver (FS-R6B):
    CH1 (steering) signal -> Arduino D2
    CH3 (throttle) signal -> Arduino D3
    VCC  -> Arduino 5V
    GND  -> Arduino GND

  BTS7960 #1 - LEFT MOTOR:
    RPWM  -> Arduino D5
    LPWM  -> Arduino D6
    VCC   -> Arduino 5V
    GND   -> Arduino GND
    R_EN  -> Arduino 5V (tied high, always enabled)
    L_EN  -> Arduino 5V (tied high, always enabled)
    B+/B- -> motor battery
    M+/M- -> left Johnson motor

  BTS7960 #2 - RIGHT MOTOR:
    RPWM  -> Arduino D9
    LPWM  -> Arduino D10
    VCC   -> Arduino 5V
    GND   -> Arduino GND
    R_EN  -> Arduino 5V (tied high, always enabled)
    L_EN  -> Arduino 5V (tied high, always enabled)
    B+/B- -> motor battery
    M+/M- -> right Johnson motor

  All grounds (Arduino, receiver, both BTS7960 boards, battery negative)
  MUST be common.

  ============================================================================
  READ THIS BEFORE YOU FLASH:
  - Motors will NOT move until a valid receiver signal is seen AND the
    throttle stick is near center. This is intentional (see ARM logic below).
  - MAX_PWM caps every motor command to 50% of full PWM. Change MAX_PWM to
    adjust the ceiling (see the clearly marked line below).
  - Test with wheels OFF THE GROUND first. Procedure is at the bottom of
    this file, in comments.
  ============================================================================
*/

// ---------------------------------------------------------------------------
// PIN DEFINITIONS
// ---------------------------------------------------------------------------
const uint8_t PIN_CH1_STEERING = 2;   // receiver CH1 -> D2 (steering)
const uint8_t PIN_CH3_THROTTLE = 3;   // receiver CH3 -> D3 (throttle)

const uint8_t PIN_LEFT_RPWM  = 10;     // left BTS7960 RPWM
const uint8_t PIN_LEFT_LPWM  = 11;     // left BTS7960 LPWM

const uint8_t PIN_RIGHT_RPWM = 6;     // right BTS7960 RPWM
const uint8_t PIN_RIGHT_LPWM = 5;    // right BTS7960 LPWM

// ---------------------------------------------------------------------------
// MOTOR DIRECTION CORRECTION
// If a motor spins the wrong way, flip its boolean here instead of
// rewiring the BTS7960 M+/M- terminals.
// ---------------------------------------------------------------------------
const bool LEFT_MOTOR_REVERSED  = false;
const bool RIGHT_MOTOR_REVERSED = false;

// ---------------------------------------------------------------------------
// >>> PWM LIMIT — change this single constant to adjust max motor power <<<
// Arduino analogWrite() range is 0-255. MAX_PWM = 128 caps output to
// approximately 50%. This limit is enforced on the FINAL motor command,
// in both forward and reverse, AFTER mixing — not by shrinking the
// receiver input range.
// ---------------------------------------------------------------------------
const int MAX_PWM = 128;

// ---------------------------------------------------------------------------
// RC PULSE CALIBRATION
// Typical FlySky pulse widths. Adjust MIN/CENTER/MAX here if your
// transmitter/receiver combo reads differently (check with the Serial
// Monitor output this sketch prints).
// ---------------------------------------------------------------------------
const int RC_MIN    = 1000;  // microseconds, full one direction
const int RC_CENTER = 1500;  // microseconds, stick centered
const int RC_MAX     = 2000; // microseconds, full other direction

// Deadband around center (in microseconds) to prevent jitter when the
// stick is physically at rest but the signal wobbles slightly.
const int DEADBAND_US = 30;

// Any pulse outside this window is treated as invalid/noise, not a real
// command. Slightly wider than RC_MIN/RC_MAX to tolerate normal drift.
const int RC_VALID_MIN = 900;
const int RC_VALID_MAX = 2100;

// pulseIn() timeout in microseconds. If no pulse edge is seen within this
// time, pulseIn() returns 0 and we treat the channel as failed rather than
// hanging the loop.
const unsigned long PULSE_TIMEOUT_US = 25000UL; // 25 ms (~1 missed frame)

// How close to RC_CENTER the throttle must be at startup before we will
// arm the motors at all.
const int ARM_CENTER_TOLERANCE = 50;

// ---------------------------------------------------------------------------
// SMOOTHING / RAMPING
// Limits how much the commanded PWM can change per loop iteration, so
// motors ramp instead of jumping instantly to full command.
// ---------------------------------------------------------------------------
const int RAMP_STEP = 6; // max PWM change per loop pass (tune to taste)

// ---------------------------------------------------------------------------
// SERIAL DEBUG INTERVAL
// ---------------------------------------------------------------------------
const unsigned long PRINT_INTERVAL_MS = 150;

// ---------------------------------------------------------------------------
// STATE
// ---------------------------------------------------------------------------
int currentLeftPWM  = 0;   // ramped, currently-applied left command (-MAX_PWM..MAX_PWM)
int currentRightPWM = 0;   // ramped, currently-applied right command
bool armed = false;        // becomes true once startup safety condition is met
unsigned long lastPrintMs = 0;

// ---------------------------------------------------------------------------
// SETUP
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(PIN_CH1_STEERING, INPUT);
  pinMode(PIN_CH3_THROTTLE, INPUT);

  pinMode(PIN_LEFT_RPWM, OUTPUT);
  pinMode(PIN_LEFT_LPWM, OUTPUT);
  pinMode(PIN_RIGHT_RPWM, OUTPUT);
  pinMode(PIN_RIGHT_LPWM, OUTPUT);

  // Motors MUST remain stopped at startup.
  stopMotors();

  Serial.println(F("Diff-drive robot booting. Motors held at zero until"));
  Serial.println(F("valid signal is seen and throttle is centered."));
}

// ---------------------------------------------------------------------------
// LOOP
// ---------------------------------------------------------------------------
void loop() {
  // ---- 1. Read receiver channels with timeout ----
  int ch1Pulse = readChannel(PIN_CH1_STEERING);
  int ch3Pulse = readChannel(PIN_CH3_THROTTLE);

  bool ch1Valid = isPulseValid(ch1Pulse);
  bool ch3Valid = isPulseValid(ch3Pulse);
  bool signalOk = ch1Valid && ch3Valid;

  int steeringSigned = 0; // -255..255
  int throttleSigned  = 0; // -255..255

  if (signalOk) {
    steeringSigned = pulseToSigned(ch1Pulse);
    throttleSigned = -pulseToSigned(ch3Pulse);
  }

  // ---- 2. Arming logic ----
  // Only allow motor control once we've seen a valid signal AND the
  // throttle stick was near center (prevents an unexpected launch if the
  // transmitter powers on with the stick out of position, or if the
  // Arduino resets mid-flight of the stick).
  if (!armed) {
    if (signalOk && abs(ch3Pulse - RC_CENTER) <= ARM_CENTER_TOLERANCE) {
      armed = true;
      Serial.println(F(">>> ARMED: motor control enabled <<<"));
    }
  }

  // ---- 3. Failsafe: any invalid signal = immediate stop, no last-value hold ----
  int targetLeft = 0;
  int targetRight = 0;

  if (signalOk && armed) {
    // Differential mixing on the wide (-255..255) signed range.
    int mixLeft  = throttleSigned + steeringSigned;
    int mixRight = throttleSigned - steeringSigned;

    // Constrain to the actual allowed motor command range. This is what
    // enforces the 50% PWM ceiling — MAX_PWM is applied here, on the
    // final command, not by shrinking the receiver input earlier.
    targetLeft  = constrain(mixLeft,  -MAX_PWM, MAX_PWM);
    targetRight = constrain(mixRight, -MAX_PWM, MAX_PWM);
  } else {
    // Not armed, or a channel dropped out: force zero. Do NOT reuse the
    // last valid command.
    targetLeft = 0;
    targetRight = 0;
  }

  // ---- 4. Ramp actual output toward target (smoothing) ----
  currentLeftPWM  = rampTowards(currentLeftPWM, targetLeft, RAMP_STEP);
  currentRightPWM = rampTowards(currentRightPWM, targetRight, RAMP_STEP);

  // If the failsafe tripped, snap to zero immediately rather than ramping
  // down slowly — safety takes priority over smoothness.
  if (!signalOk || !armed) {
    currentLeftPWM = 0;
    currentRightPWM = 0;
  }

  // ---- 5. Drive motors ----
  driveMotor(PIN_LEFT_RPWM, PIN_LEFT_LPWM, currentLeftPWM, LEFT_MOTOR_REVERSED);
  driveMotor(PIN_RIGHT_RPWM, PIN_RIGHT_LPWM, currentRightPWM, RIGHT_MOTOR_REVERSED);

  // ---- 6. Debug output ----
  unsigned long now = millis();
  if (now - lastPrintMs >= PRINT_INTERVAL_MS) {
    lastPrintMs = now;
    printDebug(ch1Pulse, ch3Pulse, ch1Valid, ch3Valid, steeringSigned,
               throttleSigned, currentLeftPWM, currentRightPWM);
  }
}

// ---------------------------------------------------------------------------
// Reads one RC channel with a bounded timeout. Returns pulse width in
// microseconds, or 0 if no pulse was detected within PULSE_TIMEOUT_US.
// ---------------------------------------------------------------------------
int readChannel(uint8_t pin) {
  unsigned long pulse = pulseIn(pin, HIGH, PULSE_TIMEOUT_US);
  return (int)pulse; // 0 if timed out
}

// ---------------------------------------------------------------------------
// True if a pulse reading looks like a real RC signal rather than noise
// or a timeout.
// ---------------------------------------------------------------------------
bool isPulseValid(int pulseUs) {
  if (pulseUs == 0) return false; // pulseIn timed out
  if (pulseUs < RC_VALID_MIN || pulseUs > RC_VALID_MAX) return false;
  return true;
}

// ---------------------------------------------------------------------------
// Converts a raw pulse width into a signed value in roughly -255..255,
// applying the center deadband first so a stick at rest produces exactly 0.
// ---------------------------------------------------------------------------
int pulseToSigned(int pulseUs) {
  int centered = pulseUs - RC_CENTER;

  if (abs(centered) <= DEADBAND_US) {
    return 0;
  }

  // Remove the deadband from the scale so output is continuous, not a
  // sudden jump at the deadband edge.
  if (centered > 0) {
    centered -= DEADBAND_US;
    return map(centered, 0, (RC_MAX - RC_CENTER - DEADBAND_US), 0, 255);
  } else {
    centered += DEADBAND_US;
    return map(centered, 0, -(RC_CENTER - RC_MIN - DEADBAND_US), 0, -255);
  }
}

// ---------------------------------------------------------------------------
// Moves `current` toward `target` by at most `step` per call.
// ---------------------------------------------------------------------------
int rampTowards(int current, int target, int step) {
  if (current < target) {
    current += step;
    if (current > target) current = target;
  } else if (current > target) {
    current -= step;
    if (current < target) current = target;
  }
  return current;
}

// ---------------------------------------------------------------------------
// Drives a single BTS7960 channel.
// value: -MAX_PWM..+MAX_PWM (already limited by caller)
// reversed: flips direction in software instead of rewiring
//
// IMPORTANT: only ONE of RPWM/LPWM is ever written nonzero at a time.
// ---------------------------------------------------------------------------
void driveMotor(uint8_t rpwmPin, uint8_t lpwmPin, int value, bool reversed) {
  if (reversed) value = -value;

  int pwm = constrain(abs(value), 0, MAX_PWM);

  if (value > 0) {
    // Forward
    analogWrite(rpwmPin, pwm);
    analogWrite(lpwmPin, 0);
  } else if (value < 0) {
    // Reverse
    analogWrite(rpwmPin, 0);
    analogWrite(lpwmPin, pwm);
  } else {
    // Stop
    analogWrite(rpwmPin, 0);
    analogWrite(lpwmPin, 0);
  }
}

// ---------------------------------------------------------------------------
// Immediately stops both motors (used at startup and can be reused
// anywhere a hard stop is needed).
// ---------------------------------------------------------------------------
void stopMotors() {
  analogWrite(PIN_LEFT_RPWM, 0);
  analogWrite(PIN_LEFT_LPWM, 0);
  analogWrite(PIN_RIGHT_RPWM, 0);
  analogWrite(PIN_RIGHT_LPWM, 0);
  currentLeftPWM = 0;
  currentRightPWM = 0;
}

// ---------------------------------------------------------------------------
// Serial debug print.
// ---------------------------------------------------------------------------
void printDebug(int ch1, int ch3, bool ch1ok, bool ch3ok, int steer,
                 int throttle, int leftCmd, int rightCmd) {
  Serial.print(F("CH1(steer)="));
  Serial.print(ch1);
  Serial.print(ch1ok ? F(" OK") : F(" BAD"));

  Serial.print(F(" | CH3(throt)="));
  Serial.print(ch3);
  Serial.print(ch3ok ? F(" OK") : F(" BAD"));

  Serial.print(F(" | armed="));
  Serial.print(armed ? F("Y") : F("N"));

  Serial.print(F(" | steerVal="));
  Serial.print(steer);
  Serial.print(F(" throttleVal="));
  Serial.print(throttle);

  Serial.print(F(" | L="));
  Serial.print(leftCmd);
  Serial.print(F(" R="));
  Serial.println(rightCmd);
}

/*
  ============================================================================
  HOW THE RECEIVER SIGNALS ARE READ
  ----------------------------------------------------------------------------
  FS-R6B outputs standard PWM servo pulses on each channel pin: a HIGH
  pulse roughly 1000-2000us long, repeating about every 20ms. pulseIn()
  measures the width of the next HIGH pulse on a pin. We pass a timeout
  (PULSE_TIMEOUT_US) so that if the receiver stops transmitting (unbound,
  out of range, powered off), pulseIn() gives up after 25ms instead of
  blocking the whole program forever. A returned value of 0 means "no
  pulse seen" and is treated as an invalid/failed channel.

  HOW THE DIFFERENTIAL MIXING WORKS
  ----------------------------------------------------------------------------
  Both channels are first converted from raw microseconds (~1000-2000,
  centered at 1500) into a signed range of roughly -255..+255, with a
  small deadband around center so a stationary stick reads as exactly 0.

  Standard differential (tank-style) mixing is then applied:
      leftMotor  = throttle + steering
      rightMotor = throttle - steering
  This means: pure throttle drives both wheels equally in the same
  direction; pure steering (throttle centered) drives the wheels in
  OPPOSITE directions, causing a turn-in-place; and combining both
  blends smoothly between straight-line driving and turning.

  WHY THE 50% PWM LIMIT IS SAFE AND WHERE IT'S APPLIED
  ----------------------------------------------------------------------------
  MAX_PWM = 128 is applied with constrain() to the MIXED result, not to
  the raw receiver reading. This means full-scale mixing math still
  happens across the full -255..255 range (so steering authority and
  throttle response feel proportionally correct), and only the FINAL
  command sent to the motor driver is capped at ~50% of the Arduino's
  0-255 PWM range. This is deliberate: clipping late (after mixing)
  preserves the correct ratio between the two wheels during combined
  throttle+steering moves, rather than distorting it by pre-scaling the
  inputs.

  WHY BOTH RPWM/LPWM ARE NEVER NONZERO TOGETHER
  ----------------------------------------------------------------------------
  On a BTS7960, RPWM drives the motor one direction and LPWM drives it
  the other. Writing both nonzero at once is at best undefined and at
  worst can confuse or stress the driver. driveMotor() always keeps the
  unused side clamped to 0.

  FAILSAFE BEHAVIOR
  ----------------------------------------------------------------------------
  Every loop iteration re-reads and re-validates both channels from
  scratch. If EITHER channel is invalid (timed out, or a pulse width
  outside a sane 900-2100us band), both motor targets are forced to 0
  and the ramped output is snapped to 0 immediately (not ramped down),
  so a lost signal stops the robot as fast as possible. The system also
  requires the throttle to be at/near center on the FIRST valid signal
  it sees before it will "arm" at all — until then, motors are held at
  zero no matter what CH1/CH3 report.
  ============================================================================

  WIRING SUMMARY (matches the top of this file)
  ----------------------------------------------------------------------------
  Receiver CH1 -> D2      Receiver CH3 -> D3
  Left BTS7960:  RPWM D5, LPWM D6, VCC/EN pins -> 5V, GND -> GND
  Right BTS7960: RPWM D9, LPWM D10, VCC/EN pins -> 5V, GND -> GND
  All grounds common (Arduino, receiver, both drivers, motor battery -).

  ============================================================================
  SAFE TESTING PROCEDURE — DO THIS BEFORE WHEELS TOUCH THE GROUND
  ----------------------------------------------------------------------------
  1. With the motor battery DISCONNECTED, power the Arduino via USB only.
     Confirm Serial Monitor (115200 baud) shows CH1/CH3 as "BAD" with the
     transmitter off, and "OK" once the transmitter is on and bound.
  2. With transmitter on and throttle stick centered, confirm you see
     ">>> ARMED <<<" printed once, and that armed=Y appears afterward.
  3. Raise the robot so both wheels spin freely in the air, or better,
     remove the wheels entirely for this step.
  4. Connect the motor battery.
  5. Slowly move the throttle stick forward a small amount. Confirm BOTH
     wheels spin the SAME direction. If a wheel spins the wrong way,
     stop, disconnect the battery, and flip that motor's REVERSED
     boolean (LEFT_MOTOR_REVERSED / RIGHT_MOTOR_REVERSED) at the top of
     this file, then re-upload.
  6. Center the throttle, then slowly move steering left/right. Confirm
     the wheels spin in OPPOSITE directions (turn-in-place behavior) and
     that left steering turns the correct way for your frame.
  7. Test combined throttle+steering at low speed and confirm smooth,
     proportional differential response.
  8. Turn the transmitter OFF while motors are commanded to move and
     confirm both motors stop within ~25-50ms (failsafe test). Repeat by
     powering off the receiver instead.
  9. Only after all of the above pass with wheels off the ground, mount
     wheels and re-test at very low throttle in an open, clear area.
  ============================================================================
*/
