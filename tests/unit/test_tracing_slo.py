import pytest

from smart_city_security.observability import (
    ServiceLevelObjective,
    Tracer,
    evaluate_availability,
)


def test_nested_traces_preserve_parent_and_export():
    spans = []
    tracer = Tracer(spans.append)
    with tracer.span("parent") as parent, tracer.span("child") as child:
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id
    assert {span.name for span in spans} == {"parent", "child"}
    assert all(span.duration_ms >= 0 for span in spans)


def test_trace_marks_error_and_slo_computes_budget():
    spans = []
    with pytest.raises(RuntimeError), Tracer(spans.append).span("failed"):
        raise RuntimeError("failure")
    assert spans[0].status == "error"
    status = evaluate_availability(
        ServiceLevelObjective("ingestion", 0.99, 3600),
        successful=995,
        total=1000,
    )
    assert status.passed
    assert status.error_budget_remaining == pytest.approx(0.5)
