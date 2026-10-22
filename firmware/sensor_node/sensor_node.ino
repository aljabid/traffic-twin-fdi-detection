#include <Wire.h>
#include <SPI.h>
#include <RTClib.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <LiquidCrystal.h>

const uint8_t TRIG_PIN = 10, ECHO_PIN = 9;
const uint8_t LDR_PIN = A0;
const uint8_t BUZZER_PIN = 6, RED_LED = 13, GREEN_LED = 12;
const uint8_t RFID_SS = 53, RFID_RST = 5;
LiquidCrystal lcd(7, 8, 22, 24, 26, 28);
const byte ROWS = 4, COLS = 4;
char KEYS[ROWS][COLS] = {{'1','2','3','A'}, {'4','5','6','B'}, {'7','8','9','C'}, {'*','0','#','D'}};
byte ROW_PINS[ROWS] = {30, 32, 34, 36};
byte COL_PINS[COLS] = {38, 40, 42, 44};
Keypad keypad = Keypad(makeKeymap(KEYS), ROW_PINS, COL_PINS, ROWS, COLS);
RTC_DS1307 rtc;
MFRC522 rfid(RFID_SS, RFID_RST);

const unsigned long PERIOD_MS = 100;
const int LDR_SHADOW_MARGIN = 120;
float ldrBase = -1;
const float TIME_SHIFT_S = 5.0;

char deviceId[16] = "A1";
const char FAKE_ID[] = "FAKE";
int attack = 0;
bool rtcFound = false;
const unsigned long NO_RTC_EPOCH = 1760000000UL;
float lastDistance = -1;
unsigned long lastReport = 0, samples = 0, blocked = 0;

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long echo = pulseIn(ECHO_PIN, HIGH, 30000UL);
  return echo == 0 ? -1.0 : echo * 0.0343 / 2.0;
}

void readCard() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  char buf[16]; buf[0] = '\0';
  for (byte i = 0; i < rfid.uid.size && i < 7; i++) {
    char hex[3]; sprintf(hex, "%02X", rfid.uid.uidByte[i]); strcat(buf, hex);
  }
  strncpy(deviceId, buf, sizeof(deviceId) - 1);
  rfid.PICC_HaltA();
  lcd.setCursor(0, 0); lcd.print("ID "); lcd.print(deviceId); lcd.print("      ");
}

void showAttack() {
  const char* names[] = {"genuine      ", "congestion   ", "clear road   ", "time shift   ", "identity     "};
  lcd.setCursor(0, 1); lcd.print("tx: "); lcd.print(names[attack]);
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT); pinMode(LDR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT); pinMode(RED_LED, OUTPUT); pinMode(GREEN_LED, OUTPUT);
  lcd.begin(16, 2); lcd.print("SCS sensor node");
  Wire.begin();
  rtcFound = rtc.begin();
  if (!rtcFound) { lcd.setCursor(0, 1); lcd.print("RTC missing"); }
  else if (!rtc.isrunning()) rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  SPI.begin(); rfid.PCD_Init();
  Serial.println("# node ready");
  showAttack();
}

void loop() {

  samples++;
  int light = analogRead(LDR_PIN);
  if (ldrBase < 0 || light < ldrBase) ldrBase = light;
  if (light > ldrBase + LDR_SHADOW_MARGIN) blocked++;
  else ldrBase += (light - ldrBase) * 0.0005;
  char key = keypad.getKey();
  if (key >= '0' && key <= '4') { attack = key - '0'; showAttack(); }
  readCard();
  while (Serial.available()) {
    char verdict = Serial.read();
    if (verdict >= '0' && verdict <= '4') { attack = verdict - '0'; showAttack(); }
    if (verdict == 'A') { digitalWrite(RED_LED, HIGH); digitalWrite(GREEN_LED, LOW); tone(BUZZER_PIN, 2000, 80);
                          lcd.setCursor(12, 0); lcd.print("ALRM"); }
    if (verdict == 'N') { digitalWrite(RED_LED, LOW); digitalWrite(GREEN_LED, HIGH); lcd.setCursor(12, 0); lcd.print("    "); }
  }

  unsigned long now = millis();
  if (now - lastReport < PERIOD_MS) return;
  float dt = (lastReport == 0) ? PERIOD_MS / 1000.0 : (now - lastReport) / 1000.0;
  lastReport = now;

  float distance = readDistanceCm();
  if (distance < 0) distance = (lastDistance < 0) ? 0 : lastDistance;
  float speedKmh = (lastDistance < 0) ? 0 : fabs(distance - lastDistance) / dt * 0.036;
  lastDistance = distance;
  float occupancy = samples ? (float)blocked / samples : 0;
  samples = blocked = 0;
  unsigned long rtcSeconds = rtcFound ? rtc.now().unixtime() : NO_RTC_EPOCH + now / 1000UL;
  const char* id = deviceId;

  if (attack == 1) { speedKmh *= 0.2; occupancy = min(1.0f, occupancy + 0.45f); }
  if (attack == 2) { speedKmh += 3.0; occupancy = max(0.0f, occupancy - 0.35f); }
  if (attack == 3) { rtcSeconds += (unsigned long)TIME_SHIFT_S; }
  if (attack == 4) { id = FAKE_ID; }

  Serial.print("T,"); Serial.print(id); Serial.print(',');
  Serial.print(now); Serial.print(','); Serial.print(rtcSeconds); Serial.print(',');
  Serial.print(distance, 1); Serial.print(','); Serial.print(speedKmh, 3); Serial.print(',');
  Serial.print(occupancy, 3); Serial.print(','); Serial.println(attack);
}
