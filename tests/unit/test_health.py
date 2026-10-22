from smart_city_security.services.health import HealthService


def test_health_reflects_dependency_readiness():
    service = HealthService("ingestion")
    service.register("database", lambda: True)
    service.register("broker", lambda: False)
    status = service.status()
    assert status.live and not status.ready
