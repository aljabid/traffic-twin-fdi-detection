from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

_current_trace: ContextVar[str | None] = ContextVar("smart_city_trace_id", default=None)
_current_span: ContextVar[str | None] = ContextVar("smart_city_span_id", default=None)


@dataclass(slots=True)
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    started_at: str
    duration_ms: float = 0
    status: str = "ok"
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Tracer:

    def __init__(self, exporter: Callable[[Span], None] | None = None) -> None:
        self.exporter = exporter or (lambda span: None)

    @contextmanager
    def span(
        self, name: str, **attributes: str | float | bool
    ) -> Iterator[Span]:
        parent = _current_span.get()
        trace_id = _current_trace.get() or secrets.token_hex(16)
        span_id = secrets.token_hex(8)
        trace_token = _current_trace.set(trace_id)
        span_token = _current_span.set(span_id)
        value = Span(
            name,
            trace_id,
            span_id,
            parent,
            datetime.now(UTC).isoformat(),
            attributes=dict(attributes),
        )
        started = perf_counter()
        try:
            yield value
        except Exception:
            value.status = "error"
            raise
        finally:
            value.duration_ms = (perf_counter() - started) * 1000
            self.exporter(value)
            _current_span.reset(span_token)
            _current_trace.reset(trace_token)
