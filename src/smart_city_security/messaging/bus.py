from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from threading import RLock

from smart_city_security.contracts import EventEnvelope


class InMemoryEventBus:

    def __init__(self, dead_letter_limit: int = 10_000):
        self._handlers: dict[str, list[Callable[[EventEnvelope], None]]] = defaultdict(list)
        self._dead_letters: deque[tuple[EventEnvelope, str]] = deque(
            maxlen=dead_letter_limit
        )
        self._lock = RLock()

    def subscribe(
        self, event_type: str, handler: Callable[[EventEnvelope], None]
    ) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: EventEnvelope) -> int:
        with self._lock:
            handlers = tuple(self._handlers.get(event.event_type, ()))
        delivered = 0
        for handler in handlers:
            try:
                handler(event)
                delivered += 1
            except Exception as exc:
                with self._lock:
                    self._dead_letters.append((event, str(exc)))
        return delivered

    @property
    def dead_letters(self) -> tuple[tuple[EventEnvelope, str], ...]:
        with self._lock:
            return tuple(self._dead_letters)
