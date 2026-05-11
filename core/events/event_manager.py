# [DOC] FILE: core/events/event_manager.py
# [DOC] PURPOSE: In-process publish/subscribe (pub/sub) event bus.
# [DOC]
# [DOC] WHY AN EVENT BUS?
# [DOC]   Without an event bus, transaction_service_v2 would need to directly
# [DOC]   import the WebSocket manager, the anomaly logger, and any other module
# [DOC]   that needs to react to "transaction_completed". This creates tight coupling:
# [DOC]   changing the WebSocket layer would require editing the transaction service.
# [DOC]
# [DOC]   With an event bus, services fire events by name (e.g., "transaction_completed")
# [DOC]   and never know which handlers subscribed — loose coupling, easier testing.
# [DOC]
# [DOC] EVENTS USED BY THE SYSTEM:
# [DOC]   "transaction_completed" → WebSocket pushes to sender + receiver browsers
# [DOC]   "batch_approved"        → WebSocket pushes batch confirmation
# [DOC]   "anomaly_flagged"       → Anomaly logger stores ZKP proof + threshold-encrypted details
# [DOC]
# [DOC] THREAD SAFETY:
# [DOC]   _subscribers is a class-level dict shared by all instances.
# [DOC]   _lock (threading.Lock) protects subscribe() from race conditions
# [DOC]   when multiple threads register handlers at startup.
# [DOC]   emit() copies the handler list under the lock, then calls handlers
# [DOC]   outside the lock so a slow handler does not block other emitters.
"""
Event Manager - Simple Pub/Sub
Purpose: Event communication between components
"""

# [DOC] Callable: type hint for any function/lambda that can be used as an event handler
from typing import Callable, Dict, List
# [DOC] threading.Lock: mutex that ensures only one thread modifies _subscribers at a time
import threading


class EventManager:
    # [DOC] Class-level (not instance-level) attributes: ALL instances share the same
    # [DOC]   subscriber registry and lock. This makes EventManager a de-facto singleton.
    """Thread-safe event system"""

    # [DOC] _subscribers: maps event_name → list of handler callables
    # [DOC]   Example: {"transaction_completed": [ws_notify, audit_log], "anomaly_flagged": [...]}
    _subscribers: Dict[str, List[Callable]] = {}
    # [DOC] _lock: re-entrant mutex protecting writes to _subscribers
    _lock = threading.Lock()

    @classmethod
    def subscribe(cls, event_name: str, handler: Callable):
        # [DOC] Register `handler` to be called every time `event_name` is emitted.
        # [DOC] If no handlers exist yet for this event, the list is created first.
        # [DOC] The lock is held for the entire duration of the list mutation.
        """Subscribe to event"""
        with cls._lock:
            # [DOC] Lazy initialise the list for this event name if first subscriber
            if event_name not in cls._subscribers:
                cls._subscribers[event_name] = []
            cls._subscribers[event_name].append(handler)
            print(f"📡 Subscribed to: {event_name}")

    @classmethod
    def emit(cls, event_name: str, data: dict):
        # [DOC] Fire `event_name` and pass `data` to every registered handler.
        # [DOC]
        # [DOC] DESIGN NOTE — lock release before calling handlers:
        # [DOC]   The handler list is read under the lock, then the lock is released.
        # [DOC]   Handlers are called WITHOUT holding the lock so that:
        # [DOC]     (a) A slow handler (e.g., WebSocket send) does not block other emitters.
        # [DOC]     (b) A handler that calls subscribe() does not deadlock.
        # [DOC]
        # [DOC] DESIGN NOTE — error isolation:
        # [DOC]   If one handler raises, the exception is caught and logged, but the
        # [DOC]   remaining handlers still execute. A broken WebSocket handler cannot
        # [DOC]   prevent the anomaly logger from running.
        """Emit event to all subscribers"""
        with cls._lock:
            # [DOC] Copy the list so we can release the lock before iterating
            handlers = cls._subscribers.get(event_name, [])

        print(f"📤 Emitting event: {event_name} (to {len(handlers)} handlers)")

        for handler in handlers:
            try:
                # [DOC] Call each handler with the event data dict.
                # [DOC] Handlers must accept a single positional argument: the data dict.
                handler(data)
            except Exception as e:
                # [DOC] Log and continue — one failing handler must not silence others
                print(f"❌ Event handler error: {str(e)}")
