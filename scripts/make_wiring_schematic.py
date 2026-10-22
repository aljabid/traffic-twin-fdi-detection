from pathlib import Path

import schemdraw
import schemdraw.elements as elm

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures" / "fig_wiring.png"
schemdraw.config(font="Arial", fontsize=10.5, lw=1.3, color="black", bgcolor="white")

PINS = ["5V", "D10", "D9", "A0", "D13", "D12", "D6", "GND"]

with schemdraw.Drawing(show=False) as d:
    d.config(unit=2.4)
    u1 = d.add(elm.Ic(
        pins=[elm.IcPin(name=p, side="right", slot=f"{len(PINS) - i}/{len(PINS)}", anchorname=p)
              for i, p in enumerate(PINS)],
        size=(3.6, 15.4), leadlen=0.9,
        label="U1\nATmega2560\n(Arduino Mega 2560)", lblsize=10.5))

    d.add(elm.Line().at(u1.absanchors["5V"]).right(2.0))
    vcc_node = d.add(elm.Dot())
    d.add(elm.Vdd().label("+5 V"))
    d.add(elm.Line().at(vcc_node.end).right(7.4))
    top = d.here

    u2 = d.add(elm.Ic(
        pins=[elm.IcPin(name="VCC", side="left", slot="4/4", anchorname="VCC"),
              elm.IcPin(name="TRIG", side="left", slot="3/4", anchorname="TRIG"),
              elm.IcPin(name="ECHO", side="left", slot="2/4", anchorname="ECHO"),
              elm.IcPin(name="GND", side="left", slot="1/4", anchorname="GND")],
        size=(2.6, 5.4), leadlen=0.8).anchor("VCC").at(top))
    d.add(elm.Label().at((u2.absanchors["VCC"][0] + 2.1, u2.absanchors["VCC"][1] + 1.0)).label(
        "U2\nHC-SR04 ultrasonic ranger", fontsize=10.5))

    d.add(elm.Line().at(u1.absanchors["D10"]).right(5.2))
    d.add(elm.Line().toy(u2.absanchors["TRIG"]))
    d.add(elm.Line().tox(u2.absanchors["TRIG"]))

    d.add(elm.Line().at(u1.absanchors["D9"]).right(6.4))
    d.add(elm.Line().toy(u2.absanchors["ECHO"]))
    d.add(elm.Line().tox(u2.absanchors["ECHO"]))

    d.add(elm.Line().at(u2.absanchors["GND"]).left(0.6))
    d.add(elm.Line().down(0.8))
    d.add(elm.Ground())

    d.add(elm.Line().at(u1.absanchors["A0"]).right(2.0))
    d.add(elm.Photoresistor().right().label("LDR1  photoresistor", loc="bottom"))
    d.add(elm.Line().right(0.8))
    d.add(elm.Ground())

    for pin, rname, lname, colour in (("D13", "R1", "LED1", "red"), ("D12", "R2", "LED2", "green")):
        d.add(elm.Line().at(u1.absanchors[pin]).right(2.0))
        d.add(elm.Resistor().right().label(f"{rname}  220 Ω", loc="bottom"))
        d.add(elm.LED().right().label(f"{lname}  {colour}", loc="bottom"))
        d.add(elm.Line().right(0.8))
        d.add(elm.Ground())

    d.add(elm.Line().at(u1.absanchors["D6"]).right(2.0))
    bz = d.add(elm.Speaker().right().anchor("in1").label("BZ1  active buzzer", loc="right", ofst=(0.4, 0)))
    d.add(elm.Line().at(bz.absanchors["in2"]).left(0.6))
    d.add(elm.Line().down(0.6))
    d.add(elm.Ground())

    d.add(elm.Line().at(u1.absanchors["GND"]).right(1.2))
    d.add(elm.Ground())

    d.save(str(OUT), dpi=600)
print(OUT)
