from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.common.config import settings
from app.common.crypto import build_content_cipher
from app.common.event_bus import EventEnvelope, build_event_bus
from app.common.observability import install_request_metrics_middleware
from app.common.persistence import build_job_store, build_session_store
from app.common.readiness import check_http_health, summarize_checks
from app.common.schemas import (
    AsyncJobStatus,
    AsyncTurnAccepted,
    AsyncTurnJobResponse,
    DialogueTurnResponse,
    GraphSnapshot,
    GraphUpsertRequest,
    GraphUpsertResponse,
    ParseTurnRequest,
    ParseTurnResponse,
    Session,
    SessionCreateRequest,
    SuggestionRequest,
    SuggestionResponse,
    Turn,
    TurnCreateRequest,
    new_id,
)
from app.common.security import TenantContext, ensure_tenant_access, get_tenant_context

app = FastAPI(title="dialogue-service", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_request_metrics_middleware(app)

LOGGER = logging.getLogger("opentree.dialogue")

TURN_INGEST_TOPIC = "turn.ingested"
TURN_PROCESSED_TOPIC = "turn.processed"
TURN_DEAD_LETTER_TOPIC = "turn.dead_letter"

EVENT_BUS = build_event_bus()
CIPHER = build_content_cipher()
SESSION_STORE = build_session_store()
JOB_STORE = build_job_store()

WORKER_STOP = threading.Event()
WORKER_THREAD: threading.Thread | None = None
WORKER_LOCK = threading.Lock()


@app.on_event("startup")
def on_startup() -> None:
    if settings.async_pipeline_enabled:
        _start_async_worker()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if WORKER_THREAD is None:
        return
    WORKER_STOP.set()
    WORKER_THREAD.join(timeout=2.0)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "dialogue",
        "async_pipeline_enabled": str(settings.async_pipeline_enabled).lower(),
        "session_store_backend": settings.session_store_backend,
        "job_store_backend": settings.job_store_backend,
    }


@app.get("/ready")
def ready() -> dict[str, object]:
    checks = {
        "parser_service": check_http_health(f"{settings.parser_service_url}/health"),
        "graph_service": check_http_health(f"{settings.graph_service_url}/health"),
        "suggestion_service": check_http_health(f"{settings.suggestion_service_url}/health"),
        "session_store": SESSION_STORE.is_ready(),
        "job_store": JOB_STORE.is_ready(),
        "event_bus": _event_bus_ready(),
    }
    return summarize_checks(checks)


@app.post("/v1/sessions", response_model=Session)
def create_session(
    payload: SessionCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> Session:
    if payload.tenant_id:
        ensure_tenant_access(payload.tenant_id, tenant)
    session = Session(tenant_id=tenant.tenant_id, user_id=payload.user_id, metadata=payload.metadata)
    SESSION_STORE.create_session(session)
    return session


@app.get("/v1/sessions/{session_id}/turns", response_model=list[Turn])
def list_turns(
    session_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[Turn]:
    _require_session(session_id=session_id, tenant_id=tenant.tenant_id)
    return _materialize_turns(tenant_id=tenant.tenant_id, session_id=session_id)


@app.post("/v1/sessions/{session_id}/turns", response_model=DialogueTurnResponse)
def add_turn(
    session_id: str,
    payload: TurnCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> DialogueTurnResponse:
    _require_session(session_id=session_id, tenant_id=tenant.tenant_id)

    history = _materialize_turns(tenant_id=tenant.tenant_id, session_id=session_id)[-12:]
    turn = Turn(
        tenant_id=tenant.tenant_id,
        session_id=session_id,
        speaker=payload.speaker,
        content=payload.content,
        parent_turn_id=payload.parent_turn_id,
    )
    _store_turn(turn)

    response = _run_pipeline(
        tenant_id=tenant.tenant_id,
        session_id=session_id,
        turn=turn,
        history=history,
        api_key=tenant.api_key,
    )
    EVENT_BUS.publish(
        TURN_PROCESSED_TOPIC,
        {
            "tenant_id": tenant.tenant_id,
            "session_id": session_id,
            "turn_id": turn.turn_id,
            "status": AsyncJobStatus.COMPLETED.value,
        },
    )
    return response


@app.post("/v1/sessions/{session_id}/turns/async", response_model=AsyncTurnAccepted)
def add_turn_async(
    session_id: str,
    payload: TurnCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> AsyncTurnAccepted:
    if not settings.async_pipeline_enabled:
        raise HTTPException(status_code=409, detail="Async pipeline is disabled")
    _require_session(session_id=session_id, tenant_id=tenant.tenant_id)

    history = _materialize_turns(tenant_id=tenant.tenant_id, session_id=session_id)[-12:]
    turn = Turn(
        tenant_id=tenant.tenant_id,
        session_id=session_id,
        speaker=payload.speaker,
        content=payload.content,
        parent_turn_id=payload.parent_turn_id,
    )
    _store_turn(turn)

    job_id = new_id("job")
    job = AsyncTurnJobResponse(
        job_id=job_id,
        tenant_id=tenant.tenant_id,
        session_id=session_id,
        turn_id=turn.turn_id,
        status=AsyncJobStatus.QUEUED,
    )
    JOB_STORE.create_job(job)

    EVENT_BUS.publish(
        TURN_INGEST_TOPIC,
        {
            "job_id": job_id,
            "tenant_id": tenant.tenant_id,
            "session_id": session_id,
            "turn": turn.model_dump(mode="json"),
            "history": [h.model_dump(mode="json") for h in history],
            "api_key": tenant.api_key,
        },
        key=turn.turn_id,
    )
    return AsyncTurnAccepted(job_id=job_id, tenant_id=tenant.tenant_id, session_id=session_id, turn_id=turn.turn_id)


@app.get("/v1/pipeline/jobs/{job_id}", response_model=AsyncTurnJobResponse)
def get_pipeline_job(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> AsyncTurnJobResponse:
    result = JOB_STORE.get_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    ensure_tenant_access(result.tenant_id, tenant)
    return result


@app.get("/v1/sessions/{session_id}/context-path")
def context_path(
    session_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, list[dict[str, str | None]]]:
    _require_session(session_id=session_id, tenant_id=tenant.tenant_id)
    path = []
    for turn in _materialize_turns(tenant_id=tenant.tenant_id, session_id=session_id):
        path.append(
            {
                "turn_id": turn.turn_id,
                "speaker": turn.speaker.value,
                "parent_turn_id": turn.parent_turn_id,
            }
        )
    return {"session_id": session_id, "path": path}


@app.get("/v1/sessions/{session_id}/graph", response_model=GraphSnapshot)
def get_session_graph(
    session_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> GraphSnapshot:
    _require_session(session_id=session_id, tenant_id=tenant.tenant_id)
    with httpx.Client(timeout=2.0) as client:
        response = client.get(
            f"{settings.graph_service_url}/v1/graph/{session_id}",
            headers=_service_headers(tenant_id=tenant.tenant_id, api_key=tenant.api_key),
        )
    response.raise_for_status()
    return GraphSnapshot.model_validate(response.json())


def _store_turn(turn: Turn) -> None:
    SESSION_STORE.append_turn(turn=turn, content_ciphertext=CIPHER.encrypt(turn.content))


def _materialize_turns(tenant_id: str, session_id: str) -> list[Turn]:
    rows = SESSION_STORE.list_turns(tenant_id=tenant_id, session_id=session_id)
    out: list[Turn] = []
    for row in rows:
        out.append(
            Turn(
                turn_id=row.turn_id,
                tenant_id=row.tenant_id,
                session_id=row.session_id,
                speaker=row.speaker,
                content=CIPHER.decrypt(row.content_ciphertext),
                parent_turn_id=row.parent_turn_id,
                created_at=row.created_at,
            )
        )
    return out


def _require_session(session_id: str, tenant_id: str) -> Session:
    session = SESSION_STORE.get_session(tenant_id=tenant_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _run_pipeline(
    tenant_id: str,
    session_id: str,
    turn: Turn,
    history: list[Turn],
    api_key: str | None,
) -> DialogueTurnResponse:
    parse_result = _call_parser(
        tenant_id=tenant_id,
        session_id=session_id,
        turn=turn,
        history=history,
        api_key=api_key,
    )
    graph_result = _call_graph(tenant_id=tenant_id, parse_result=parse_result, api_key=api_key)
    suggestion_result = _call_suggestion(
        tenant_id=tenant_id,
        session_id=session_id,
        parse_result=parse_result,
        api_key=api_key,
    )
    return DialogueTurnResponse(
        turn=turn,
        parse=parse_result,
        graph_update=graph_result,
        suggested_questions=suggestion_result.suggestions,
    )


def _call_parser(
    tenant_id: str,
    session_id: str,
    turn: Turn,
    history: list[Turn],
    api_key: str | None,
) -> ParseTurnResponse:
    payload = ParseTurnRequest(tenant_id=tenant_id, session_id=session_id, turn=turn, history=history)
    with httpx.Client(timeout=2.0) as client:
        response = client.post(
            f"{settings.parser_service_url}/v1/parse/turn",
            json=payload.model_dump(mode="json"),
            headers=_service_headers(tenant_id=tenant_id, api_key=api_key),
        )
    response.raise_for_status()
    return ParseTurnResponse.model_validate(response.json())


def _call_graph(tenant_id: str, parse_result: ParseTurnResponse, api_key: str | None) -> GraphUpsertResponse:
    request = GraphUpsertRequest(
        tenant_id=tenant_id,
        session_id=parse_result.session_id,
        concepts=parse_result.concepts,
        relations=parse_result.relations,
    )
    with httpx.Client(timeout=2.0) as client:
        response = client.post(
            f"{settings.graph_service_url}/v1/graph/upsert",
            json=request.model_dump(mode="json"),
            headers=_service_headers(tenant_id=tenant_id, api_key=api_key),
        )
    response.raise_for_status()
    return GraphUpsertResponse.model_validate(response.json())


def _call_suggestion(
    tenant_id: str,
    session_id: str,
    parse_result: ParseTurnResponse,
    api_key: str | None,
) -> SuggestionResponse:
    request = SuggestionRequest(
        tenant_id=tenant_id,
        session_id=session_id,
        knowledge_gaps=parse_result.knowledge_gaps,
    )
    with httpx.Client(timeout=2.0) as client:
        response = client.post(
            f"{settings.suggestion_service_url}/v1/suggestions/questions",
            json=request.model_dump(mode="json"),
            headers=_service_headers(tenant_id=tenant_id, api_key=api_key),
        )
    response.raise_for_status()
    return SuggestionResponse.model_validate(response.json())


def _service_headers(tenant_id: str, api_key: str | None) -> dict[str, str]:
    headers = {"X-Tenant-ID": tenant_id}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _event_bus_ready() -> tuple[bool, str]:
    try:
        EVENT_BUS.publish(
            "health.ping",
            {"sent_at": datetime.now(timezone.utc).isoformat()},
            key="dialogue",
        )
        return True, "event bus ready"
    except Exception as exc:
        return False, f"event bus not ready: {exc}"


def _start_async_worker() -> None:
    global WORKER_THREAD
    with WORKER_LOCK:
        if WORKER_THREAD and WORKER_THREAD.is_alive():
            return
        WORKER_STOP.clear()
        worker_name = f"dialogue-{uuid4().hex[:8]}"
        WORKER_THREAD = threading.Thread(
            target=_consume_turn_events,
            kwargs={"consumer_name": worker_name},
            daemon=True,
        )
        WORKER_THREAD.start()


def _consume_turn_events(consumer_name: str) -> None:
    while not WORKER_STOP.is_set():
        messages = EVENT_BUS.consume(
            topic=TURN_INGEST_TOPIC,
            consumer_group=settings.event_bus_consumer_group,
            consumer_name=consumer_name,
            count=20,
            block_ms=500,
        )
        if not messages:
            continue
        for message in messages:
            _handle_turn_event(message)
        EVENT_BUS.ack(topic=TURN_INGEST_TOPIC, consumer_group=settings.event_bus_consumer_group, messages=messages)


def _handle_turn_event(message: EventEnvelope) -> None:
    payload = message.payload
    job_id = str(payload.get("job_id", ""))
    job = JOB_STORE.get_job(job_id)
    if not job:
        return

    JOB_STORE.upsert_job(job.model_copy(update={"status": AsyncJobStatus.PROCESSING}))
    max_attempts = max(settings.async_retry_max_attempts, 1)
    base_delay = max(settings.async_retry_base_delay_seconds, 0.05)
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            turn = Turn.model_validate(payload["turn"])
            history = [Turn.model_validate(item) for item in payload.get("history", [])]
            tenant_id = str(payload["tenant_id"])
            session_id = str(payload["session_id"])
            api_key = payload.get("api_key")
            result = _run_pipeline(
                tenant_id=tenant_id,
                session_id=session_id,
                turn=turn,
                history=history,
                api_key=str(api_key) if api_key else None,
            )
            JOB_STORE.upsert_job(
                AsyncTurnJobResponse(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    turn_id=turn.turn_id,
                    status=AsyncJobStatus.COMPLETED,
                    result=result,
                )
            )
            EVENT_BUS.publish(
                TURN_PROCESSED_TOPIC,
                {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "turn_id": turn.turn_id,
                    "status": AsyncJobStatus.COMPLETED.value,
                },
                key=turn.turn_id,
            )
            return
        except Exception as exc:
            last_error = str(exc)
            LOGGER.exception(
                "async_turn_attempt_failed job_id=%s attempt=%s/%s error=%s",
                job_id,
                attempt,
                max_attempts,
                last_error,
            )
            if attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))

    failed_job = job.model_copy(update={"status": AsyncJobStatus.FAILED, "error": last_error})
    JOB_STORE.upsert_job(failed_job)
    EVENT_BUS.publish(
        TURN_DEAD_LETTER_TOPIC,
        {
            "job_id": failed_job.job_id,
            "tenant_id": failed_job.tenant_id,
            "session_id": failed_job.session_id,
            "turn_id": failed_job.turn_id,
            "status": failed_job.status.value,
            "error": failed_job.error,
            "payload": payload,
        },
        key=failed_job.turn_id,
    )
