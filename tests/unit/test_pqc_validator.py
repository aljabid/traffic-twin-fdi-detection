from smart_city_security.integration.pqc_validator import validate_native_pqc


def test_pqc_validator_reports_availability_without_crashing():
    report = validate_native_pqc(repetitions=1)
    assert isinstance(report["passed"], bool)
