"""
Event Manager - Simple Pub/Sub
Author: Ashutosh Rajesh
Purpose: Event communication between components
"""

from typing import Callable, Dict, List
import threading


class EventManager:
    """Thread-safe event system"""
    
    _subscribers: Dict[str, List[Callable]] = {}
    _lock = threading.Lock()
    
    @classmethod
    def subscribe(cls, event_name: str, handler: Callable):
        """Subscribe to event"""
        with cls._lock:
            if event_name not in cls._subscribers:
                cls._subscribers[event_name] = []
            cls._subscribers[event_name].append(handler)
            print(f"📡 Subscribed to: {event_name}")
    
    @classmethod
    def emit(cls, event_name: str, data: dict):
        """Emit event to all subscribers"""
        with cls._lock:
            handlers = cls._subscribers.get(event_name, [])
        
        print(f"📤 Emitting event: {event_name} (to {len(handlers)} handlers)")
        
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                print(f"❌ Event handler error: {str(e)}")