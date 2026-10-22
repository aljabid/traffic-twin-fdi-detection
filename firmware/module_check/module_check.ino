#include <Wire.h>
#include <SPI.h>
#include <RTClib.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <LiquidCrystal.h>

const uint8_t TRIG_PIN = 10, ECHO_PIN = 9, LDR_PIN = A0, BUZZER_PIN = 6, RED_LED = 13, GREEN_LED = 12;
LiquidCrystal lcd(7, 8, 22, 24, 26, 28);
const byte ROWS = 4, COLS = 4;
char KEYS[ROWS][COLS] = {{'1','2','3','A'}, {'4','5','6','B'}, {'7','8','9','C'}, {'*','0','#','D'}};
byte ROW_PINS[ROWS] = {30, 32, 34, 36};
byte COL_PINS[COLS] = {38, 40, 42, 44};
Keypad keypad = Keypad(makeKeymap(KEYS), ROW_PINS, COL_PINS, ROWS, COLS);
RTC_DS1307 rtc;
MFRC522 rfid(53, 5);
bool rtcFound = false;
char lastKey = '-';
char uid[16] = "-";
unsigned long lastPrint = 0;

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT); pinMode(LDR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT); pinMode(RED_LED, OUTPUT); pinMode(GREEN_LED, OUTPUT);
  lcd.begin(16, 2); lcd.print("module check");
  Wire.begin();
  rtcFound = rtc.begin();
  if (rtcFound && !rtc.isrunning()) rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  SPI.begin(); rfid.PCD_Init();
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print("# rfid version 0x"); Serial.println(version, HEX);
  Serial.print("# rtc "); Serial.println(rtcFound ? "found" : "not found");

  digitalWrite(RED_LED, HIGH); tone(BUZZER_PIN, 2000, 150); delay(300);
  digitalWrite(RED_LED, LOW); digitalWrite(GREEN_LED, HIGH); delay(300); digitalWrite(GREEN_LED, LOW);
}

void loop() {
  char key = keypad.getKey();
  if (key) { lastKey = key; tone(BUZZER_PIN, 1500, 40); }
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    uid[0] = '\0';
    for (byte i = 0; i < rfid.uid.size && i < 7; i++) { char hex[3]; sprintf(hex, "%02X", rfid.uid.uidByte[i]); strcat(uid, hex); }
    rfid.PICC_HaltA();
  }
  if (millis() - lastPrint < 500) return;
  lastPrint = millis();

  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10); digitalWrite(TRIG_PIN, LOW);
  unsigned long echo = pulseIn(ECHO_PIN, HIGH, 30000UL);
  int light = analogRead(LDR_PIN);

  Serial.print("C,");
  if (echo) Serial.print(echo * 0.0343 / 2.0, 1); else Serial.print('-');
  Serial.print(','); Serial.print(light); Serial.print(',');
  if (rtcFound) Serial.print(rtc.now().unixtime()); else Serial.print('-');
  Serial.print(','); Serial.print(lastKey); Serial.print(','); Serial.println(uid);

  lcd.setCursor(0, 1);
  lcd.print("d="); if (echo) lcd.print((int)(echo * 0.0343 / 2.0)); else lcd.print('-');
  lcd.print(" L="); lcd.print(light); lcd.print(" k="); lcd.print(lastKey); lcd.print("   ");
}
