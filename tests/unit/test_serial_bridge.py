import math

from smart_city_security.hardware.serial_bridge import LiveScorer, fit, parse, readings


def _lines(n, start=1_760_000_000):
    out = ["# boot", "garbage"]
    for i in range(n):
        position = 100 + 60 * math.sin(i / 40)
        speed = abs(60 * math.cos(i / 40) / 40) * 10 * 0.036
        occupancy = 0.6 if (i // 25) % 2 else 0.1
        out.append(f"T,AB12,{i * 100},{start + i // 10},{position:.1f},{speed:.3f},{occupancy},0")
    return out


def test_parse_maps_fields_and_rejects_noise():
    reading = parse("T,AB12,1250,1760000000,150.0,3.6,0.4,1", 7)
    assert reading.telemetry.device_id == "node-AB12"
    assert reading.telemetry.timestamp == 1760000000.25
    assert reading.telemetry.position == 1.5 and reading.telemetry.speed == 3.6
    assert reading.attack == 1 and reading.telemetry.sequence_number == 7
    assert parse("hello", 1) is None and parse("T,1,2,3", 1) is None and parse("T,a,x,1,2,3,4,0", 1) is None
    assert [r.telemetry.sequence_number for r in readings(_lines(3))] == [1, 2, 3]


def test_millis_clock_ignores_a_stuck_rtc_and_continues_after_a_reset():
    lines = ["T,AB12,1500,1760000000,1,1,0,0", "T,AB12,2600,1760000000,1,1,0,0",
             "T,AB12,100,1760000000,1,1,0,0"]
    stamps = [r.telemetry.timestamp for r in readings(lines, clock="millis")]
    assert stamps[:2] == [1760000001.5, 1760000002.6]
    assert stamps[2] > stamps[1]
    assert parse(lines[1], 1, clock="rtc").telemetry.timestamp == 1760000000.6


def test_fit_and_live_scoring_on_a_recording():
    stream = [r.telemetry for r in readings(_lines(4000))]
    scorer = LiveScorer(fit(stream[:3500]))
    benign_flags = [scorer.score(m) for m in stream[3500:3700]]
    assert sum(benign_flags) / len(benign_flags) < 0.3
    forged = parse("T,AB12,999999,1760000400,100.0,80.0,0.95,1", 99999)
    assert isinstance(scorer.score(forged.telemetry), bool)


def test_schedule_offsets():
    from smart_city_security.hardware.serial_bridge import parse_schedule

    assert parse_schedule("0:30,1:20,0:10") == [(0.0, 0), (30.0, 1), (50.0, 0), (60.0, -1)]
