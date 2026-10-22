import pytest

from smart_city_security.evaluation.link_budget import (
    LATENCY_BUDGET_MS,
    LINKS,
    Link,
    SuiteSizes,
    analyse,
    link_cost,
)

SMALL = SuiteSizes("small", message_bytes=500, handshake_bytes=100, messages_per_session=50)


def test_airtime_is_bits_over_rate():
    cost = link_cost(SMALL, Link("1 kbit/s", 1_000))
    assert cost["message_airtime_ms"] == pytest.approx(4_000.0)
    assert cost["handshake_airtime_ms"] == pytest.approx(800.0)
    assert cost["within_latency_budget"] is False


def test_fragments_round_up():
    assert link_cost(SMALL, Link("frame", 1e6, max_payload_bytes=127))["frames_per_message"] == 4
    assert link_cost(SMALL, Link("no-frame-limit", 1e6))["frames_per_message"] == 1


def test_rate_includes_amortised_handshake_and_duty_cycle():
    per_message_bits = (500 + 100 / 50) * 8
    free = link_cost(SMALL, Link("free", 8_000))
    capped = link_cost(SMALL, Link("capped", 8_000, duty_cycle=0.01))
    assert free["max_messages_per_second"] == pytest.approx(8_000 / per_message_bits)
    assert capped["max_messages_per_second"] == pytest.approx(free["max_messages_per_second"] * 0.01)
    assert capped["min_seconds_between_messages"] == pytest.approx(0.5 / 0.01)


def test_budget_boundary():
    exact = SuiteSizes("exact", message_bytes=1_250, handshake_bytes=0, messages_per_session=1)
    assert link_cost(exact, Link("100k", 100_000))["message_airtime_ms"] == pytest.approx(LATENCY_BUDGET_MS)
    assert link_cost(exact, Link("100k", 100_000))["within_latency_budget"] is True


def test_analyse_covers_every_link_and_suite():
    report = analyse([SMALL, SuiteSizes("big", 5_000, 2_000, 50)])
    assert len(report["rows"]) == 2 * len(LINKS)
    assert {r["suite"] for r in report["rows"]} == {"small", "big"}
    for link in LINKS:
        small, big = (r for r in report["rows"] if r["link"] == link.name)
        assert big["message_airtime_ms"] > small["message_airtime_ms"]
