#define AIN1 7
#define AIN2 8
#define PWMA 9
#define STBY 10

void setup() {
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);
  pinMode(PWMA, OUTPUT);
  pinMode(STBY, OUTPUT);

  // Enable TB6612FNG
  digitalWrite(STBY, HIGH);

  // One direction
  digitalWrite(AIN1, HIGH);
  digitalWrite(AIN2, LOW);

  // 50% PWM
  analogWrite(PWMA, 128);
}

void loop() {
  // Motor runs continuously
}