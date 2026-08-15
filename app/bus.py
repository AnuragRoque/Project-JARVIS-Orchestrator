"""A tiny in-process publish/subscribe event bus.

Modules never import each other; they communicate through typed string events on
this bus (see docs/ARCHITECTURE.md §6 and docs/MODULE_CONTRACT.md). Handlers run
synchronously in the publisher's thread; UI subscribers are responsible for
marshalling to the GUI thread (e.g. via a queued Qt signal).
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable

from .logsetup import get_logger

log = get_logger("bus")

Handler = Callable[..., None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler`` for ``event``. Returns an unsubscribe callable."""
        with self._lock:
            self._subs[event].append(handler)

        def _unsub() -> None:
            self.unsubscribe(event, handler)

        return _unsub

    def once(self, event: str, handler: Handler) -> None:
        """Subscribe for a single delivery, then auto-unsubscribe."""
        def _wrapper(*args, **kwargs) -> None:
            self.unsubscribe(event, _wrapper)
            handler(*args, **kwargs)

        self.subscribe(event, _wrapper)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._subs.get(event)
            if handlers and handler in handlers:
                handlers.remove(handler)

    def publish(self, event: str, *args, **kwargs) -> None:
        """Deliver ``event`` to all subscribers. Handler errors are logged, never raised."""
        with self._lock:
            handlers = list(self._subs.get(event, ()))
        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception:
                log.exception("Subscriber for %r failed", event)


# Process-wide default bus.
bus = EventBus()
