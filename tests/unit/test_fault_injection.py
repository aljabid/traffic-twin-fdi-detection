from smart_city_security.resilience import FaultScenario, run_fault_campaign


def test_fault_campaign_verifies_safe_recovery():
    state = {"safe": True}
    scenario = FaultScenario(
        "dependency loss",
        "advisory degraded mode",
        1,
        inject=lambda: state.update(safe=True),
        recover=lambda: state.update(safe=True),
        verify_safe=lambda: state["safe"],
    )
    assert run_fault_campaign([scenario])["passed"]
