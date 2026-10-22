from smart_city_security.security.audit import AuditLog


def test_audit_event_is_recorded():
    audit = AuditLog()
    audit.record("message_rejected", "device-1", "failure", "replay")
    assert audit.events[0].outcome == "failure"
