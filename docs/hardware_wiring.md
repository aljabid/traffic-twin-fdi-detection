# Sensor node wiring (ELEGOO Mega 2560 kit)

Matches the pin constants in firmware/sensor_node/sensor_node.ino. Build
it one module at a time and test each before adding the next. Unplug the USB
cable whenever you change wires.

## Power rails

Mega 5V → breadboard red (+) rail; Mega GND → blue (−) rail. Every
"5V" and "GND" below means these rails, except the RFID reader, which takes
3.3V from the Mega's 3.3V pin.

## Modules

| Module | Module pin → Mega pin |
|---|---|
| HC-SR04 ultrasonic | VCC → 5V; Trig → D10; Echo → D9; GND → GND (as built on the bench) |
| Light gate (photoresistor, shadow detector) | one leg → A0, other leg → GND; no resistor (the Mega's internal pull-up on A0 is enabled in code). Room light from above; a passing object shades it and the reading rises (as built on the bench) |
| LCD1602 (parallel, 16 pins) | 1 VSS → GND; 2 VDD → 5V; 3 V0 → middle pin of the 10 kΩ potentiometer (outer pins to 5V and GND); 4 RS → D7; 5 RW → GND; 6 E → D8; 11 D4 → D22; 12 D5 → D24; 13 D6 → D26; 14 D7 → D28; 15 A → 220 Ω → 5V; 16 K → GND. Pins 7-10 unused |
| DS1307 RTC | VCC → 5V; GND → GND; SDA → D20; SCL → D21. Fit a CR2032 coin cell if the module has a holder (not in the kit) |
| 4×4 membrane keypad | 8 wires, left to right: rows → D30, D32, D34, D36; columns → D38, D40, D42, D44 |
| RC522 RFID | 3.3V → 3.3V (not 5V); GND → GND; RST → D5; SDA (SS) → D53; SCK → D52; MOSI → D51; MISO → D50; IRQ unused |
| Active buzzer | + (long leg) → D6; − → GND |
| Red LED | long leg → 220 Ω → D13; short leg → GND (as built on the bench) |
| Green LED | long leg → 220 Ω → D12; short leg → GND (as built on the bench) |

Resistor colour codes: 220 Ω = red-red-brown; 10 kΩ = brown-black-orange.

Not used yet: GY-521 accelerometer, PIR, rotary encoder, motors.

## Bring-up order

1. Board alone on USB: blink test (confirms driver, port, upload).
2. Ultrasonic: distances print over serial as a hand moves.
3. LCD: text appears (turn the potentiometer until it does).
4. Light gate: occupancy rises when a card blocks the beam; set
   LDR_BLOCKED_BELOW from the printed readings.
5. RTC, keypad, RFID, buzzer and LEDs.
6. Full firmware: lines T,... at 10 Hz; keys 0-4 change the attack shown
   on the LCD.

## Scene

Fix the ultrasonic sensor at one end of a 40-60 cm track and the light gate
halfway along it. A toy car (or a book moved by hand) running along the
track stands in for traffic: distance gives position and speed; the gate
gives occupancy, as a loop detector would.
