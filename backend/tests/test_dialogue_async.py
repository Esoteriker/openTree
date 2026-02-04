from __future__ import annotations

from app.common.event_bus import EventEnvelope, InMemoryEventBus
from app.common.persistence import MemoryJobStore
from app.common.schemas import (
    AsyncJobStatus,
    AsyncTurnJobResponse,
    DialogueTurnResponse,
    GraphUpsertResponse,
    ParseTurnResponse,
    SuggestionResponse,
    Turn,
)
from app.services.dialogue import main as dialogue_main


def _build_dialogue_result(turn: Turn) -> DialogueTurnResponse:
    parse = ParseTurnResponse(tenant_id=turn.tenant_id, session_id=turn.session_id, turn_id=turn.turn_id)
    graph = GraphUpsertResponse(
        tenant_id=turn.tenant_id,
        session_id=turn.session_id,
        added_nodes=0,
        merged_nodes=0,
        added_edges=0,
        merged_edges=0,
    )
    suggestion = SuggestionResponse(tenant_id=turn.tenant_id, session_id=turn.session_id, suggestions=[])
    return DialogueTurnResponse(turn=turn, parse=parse, graph_update=graph, suggested_questions=suggestion.suggestions)


def test_async_retry_then_success(monkeypatch) -> None:
    original_job_store = dialogue_main.JOB_STORE
    original_event_bus = dialogue_main.EVENT_BUS
    original_attempts = dialogue_main.settings.async_retry_max_attempts
    original_delay = dialogue_main.settings.async_retry_base_delay_seconds
    try:
        dialogue_main.JOB_STORE = MemoryJobStore()
        dialogue_main.EVENT_BUS = InMemoryEventBus()
        dialogue_main.settings.async_retry_max_attempts = 3
        dialogue_main.settings.async_retry_base_delay_seconds = 0.0

        turn = Turn(tenant_id="public", session_id="sess_demo", speaker="user", content="hello")
        job = AsyncTurnJobResponse(
            job_id="job_demo",
            tenant_id="public",
            session_id="sess_demo",
            turn_id=turn.turn_id,
            status=AsyncJobStatus.QUEUED,
        )
        dialogue_main.JOB_STORE.create_job(job)

        state = {"attempts": 0}

        def fake_run_pipeline(**kwargs):  # type: ignore[no-untyped-def]
            state["attempts"] += 1
            if state["attempts"] == 1:
                raise RuntimeError("transient")
            return _build_dialogue_result(kwargs["turn"])

        monkeypatch.setattr(dialogue_main, "_run_pipeline", fake_run_pipeline)
        message = EventEnvelope(
            message_id="m1",
            topic="turn.ingested",
            key=turn.turn_id,
            payload={
                "job_id": "job_demo",
                "tenant_id": "public",
                "session_id": "sess_demo",
                "turn": turn.model_dump(mode="json"),
                "history": [],
                "api_key": None,
            },
        )
        dialogue_main._handle_turn_event(message)

        result = dialogue_main.JOB_STORE.get_job("job_demo")
        assert result is not None
        assert result.status == AsyncJobStatus.COMPLETED
        assert state["attempts"] == 2
    finally:
        dialogue_main.JOB_STORE = original_job_store
        dialogue_main.EVENT_BUS = original_event_bus
        dialogue_main.settings.async_retry_max_attempts = original_attempts
        dialogue_main.settings.async_retry_base_delay_seconds = original_delay


def test_async_dead_letter_after_max_retries(monkeypatch) -> None:
    original_job_store = dialogue_main.JOB_STORE
    original_event_bus = dialogue_main.EVENT_BUS
    original_attempts = dialogue_main.settings.async_retry_max_attempts
    original_delay = dialogue_main.settings.async_retry_base_delay_seconds
    try:
        bus = InMemoryEventBus()
        dialogue_main.JOB_STORE = MemoryJobStore()
        dialogue_main.EVENT_BUS = bus
        dialogue_main.settings.async_retry_max_attempts = 2
        dialogue_main.settings.async_retry_base_delay_seconds = 0.0

        turn = Turn(tenant_id="public", session_id="sess_demo", speaker="user", content="hello")
        job = AsyncTurnJobResponse(
            job_id="job_fail",
            tenant_id="public",
            session_id="sess_demo",
            turn_id=turn.turn_id,
            status=AsyncJobStatus.QUEUED,
        )
        dialogue_main.JOB_STORE.create_job(job)

        def always_fail(**kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("persistent-failure")

        monkeypatch.setattr(dialogue_main, "_run_pipeline", always_fail)
        message = EventEnvelope(
            message_id="m2",
            topic="turn.ingested",
            key=turn.turn_id,
            payload={
                "job_id": "job_fail",
                "tenant_id": "public",
                "session_id": "sess_demo",
                "turn": turn.model_dump(mode="json"),
                "history": [],
                "api_key": None,
            },
        )
        dialogue_main._handle_turn_event(message)

        result = dialogue_main.JOB_STORE.get_job("job_fail")
        assert result is not None
        assert result.status == AsyncJobStatus.FAILED

        dlq_messages = bus.consume("turn.dead_letter", consumer_group="test", consumer_name="test", block_ms=0)
        assert len(dlq_messages) == 1
    finally:
        dialogue_main.JOB_STORE = original_job_store
        dialogue_main.EVENT_BUS = original_event_bus
        dialogue_main.settings.async_retry_max_attempts = original_attempts
        dialogue_main.settings.async_retry_base_delay_seconds = original_delay
