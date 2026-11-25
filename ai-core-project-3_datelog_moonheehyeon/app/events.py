"""이벤트 발행·구독. 구독자 장애가 메인 Agent를 중단하지 않는다."""
from copy import deepcopy
from uuid import uuid4
from . import store

class EventBus:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def emit(self, session_id, run_id, event_type, data):
        event = {'event_id': uuid4().hex, 'session_id': session_id, 'run_id': run_id, 'type': event_type, 'timestamp': store.now(), 'data': deepcopy(data)}
        for subscriber in self.subscribers:
            try:
                subscriber(deepcopy(event))
            except Exception:
                continue
        return event

class LoggingAgent:
    """LLM 없이 발생한 이벤트를 그대로 세션별로 저장한다."""
    def __call__(self, event):
        store.append_event(event)

bus = EventBus()
bus.subscribe(LoggingAgent())
