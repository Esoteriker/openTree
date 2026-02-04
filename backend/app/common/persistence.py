from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.common.config import settings
from app.common.schemas import AsyncTurnJobResponse, Session, Speaker, Turn

try:
    import psycopg2
    from psycopg2.extras import Json
except Exception:  # pragma: no cover - optional dependency fallback
    psycopg2 = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]

try:
    from redis import Redis
except Exception:  # pragma: no cover - optional dependency fallback
    Redis = None  # type: ignore[assignment]


@dataclass
class StoredTurnRecord:
    turn_id: str
    tenant_id: str
    session_id: str
    speaker: Speaker
    parent_turn_id: str | None
    created_at: datetime
    content_ciphertext: str


class SessionStore:
    def create_session(self, session: Session) -> None:
        raise NotImplementedError

    def get_session(self, tenant_id: str, session_id: str) -> Session | None:
        raise NotImplementedError

    def append_turn(self, turn: Turn, content_ciphertext: str) -> None:
        raise NotImplementedError

    def list_turns(self, tenant_id: str, session_id: str) -> list[StoredTurnRecord]:
        raise NotImplementedError

    def is_ready(self) -> tuple[bool, str]:
        raise NotImplementedError


class JobStore:
    def create_job(self, job: AsyncTurnJobResponse) -> None:
        raise NotImplementedError

    def upsert_job(self, job: AsyncTurnJobResponse) -> None:
        raise NotImplementedError

    def get_job(self, job_id: str) -> AsyncTurnJobResponse | None:
        raise NotImplementedError

    def is_ready(self) -> tuple[bool, str]:
        raise NotImplementedError


class MemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._turns: dict[str, list[StoredTurnRecord]] = {}

    @staticmethod
    def _scope_key(tenant_id: str, session_id: str) -> str:
        return f"{tenant_id}:{session_id}"

    def create_session(self, session: Session) -> None:
        self._sessions[self._scope_key(session.tenant_id, session.session_id)] = session

    def get_session(self, tenant_id: str, session_id: str) -> Session | None:
        return self._sessions.get(self._scope_key(tenant_id, session_id))

    def append_turn(self, turn: Turn, content_ciphertext: str) -> None:
        scope = self._scope_key(turn.tenant_id, turn.session_id)
        rows = self._turns.setdefault(scope, [])
        rows.append(
            StoredTurnRecord(
                turn_id=turn.turn_id,
                tenant_id=turn.tenant_id,
                session_id=turn.session_id,
                speaker=turn.speaker,
                parent_turn_id=turn.parent_turn_id,
                created_at=turn.created_at,
                content_ciphertext=content_ciphertext,
            )
        )

    def list_turns(self, tenant_id: str, session_id: str) -> list[StoredTurnRecord]:
        return list(self._turns.get(self._scope_key(tenant_id, session_id), []))

    def is_ready(self) -> tuple[bool, str]:
        return True, "memory session store ready"


class PostgresSessionStore(SessionStore):
    def __init__(self, dsn: str) -> None:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required for postgres session store backend")
        self._dsn = dsn
        self._ensure_schema()

    def _connect(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not available")
        return psycopg2.connect(self._dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dialogue_sessions (
                        tenant_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        metadata JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (tenant_id, session_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dialogue_turns (
                        tenant_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        speaker TEXT NOT NULL,
                        parent_turn_id TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        content_ciphertext TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, session_id, turn_id),
                        CONSTRAINT fk_turn_session
                            FOREIGN KEY (tenant_id, session_id)
                            REFERENCES dialogue_sessions(tenant_id, session_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_dialogue_turns_lookup
                    ON dialogue_turns (tenant_id, session_id, created_at, turn_id)
                    """
                )

    def create_session(self, session: Session) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dialogue_sessions(tenant_id, session_id, user_id, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, session_id) DO UPDATE
                    SET user_id = EXCLUDED.user_id, metadata = EXCLUDED.metadata, created_at = EXCLUDED.created_at
                    """,
                    (
                        session.tenant_id,
                        session.session_id,
                        session.user_id,
                        Json(session.metadata) if Json else json.dumps(session.metadata),
                        session.created_at,
                    ),
                )

    def get_session(self, tenant_id: str, session_id: str) -> Session | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id, session_id, user_id, metadata, created_at
                    FROM dialogue_sessions
                    WHERE tenant_id = %s AND session_id = %s
                    """,
                    (tenant_id, session_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                metadata = row[3] if isinstance(row[3], dict) else {}
                return Session(
                    tenant_id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    metadata=metadata,
                    created_at=row[4],
                )

    def append_turn(self, turn: Turn, content_ciphertext: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dialogue_turns(
                        tenant_id, session_id, turn_id, speaker, parent_turn_id, created_at, content_ciphertext
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, session_id, turn_id) DO UPDATE
                    SET speaker = EXCLUDED.speaker,
                        parent_turn_id = EXCLUDED.parent_turn_id,
                        created_at = EXCLUDED.created_at,
                        content_ciphertext = EXCLUDED.content_ciphertext
                    """,
                    (
                        turn.tenant_id,
                        turn.session_id,
                        turn.turn_id,
                        turn.speaker.value,
                        turn.parent_turn_id,
                        turn.created_at,
                        content_ciphertext,
                    ),
                )

    def list_turns(self, tenant_id: str, session_id: str) -> list[StoredTurnRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT turn_id, tenant_id, session_id, speaker, parent_turn_id, created_at, content_ciphertext
                    FROM dialogue_turns
                    WHERE tenant_id = %s AND session_id = %s
                    ORDER BY created_at ASC, turn_id ASC
                    """,
                    (tenant_id, session_id),
                )
                rows = cur.fetchall()

        result: list[StoredTurnRecord] = []
        for row in rows:
            try:
                speaker = Speaker(str(row[3]))
            except ValueError:
                speaker = Speaker.USER
            result.append(
                StoredTurnRecord(
                    turn_id=row[0],
                    tenant_id=row[1],
                    session_id=row[2],
                    speaker=speaker,
                    parent_turn_id=row[4],
                    created_at=row[5],
                    content_ciphertext=row[6],
                )
            )
        return result

    def is_ready(self) -> tuple[bool, str]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True, "postgres session store ready"
        except Exception as exc:
            return False, f"postgres session store not ready: {exc}"


class MemoryJobStore(JobStore):
    def __init__(self) -> None:
        self._jobs: dict[str, AsyncTurnJobResponse] = {}

    def create_job(self, job: AsyncTurnJobResponse) -> None:
        self._jobs[job.job_id] = job

    def upsert_job(self, job: AsyncTurnJobResponse) -> None:
        self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> AsyncTurnJobResponse | None:
        return self._jobs.get(job_id)

    def is_ready(self) -> tuple[bool, str]:
        return True, "memory job store ready"


class RedisJobStore(JobStore):
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        if Redis is None:
            raise RuntimeError("redis package is required for redis job store backend")
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds
        self._prefix = f"{settings.redis_stream_prefix}:job"

    def _key(self, job_id: str) -> str:
        return f"{self._prefix}:{job_id}"

    def create_job(self, job: AsyncTurnJobResponse) -> None:
        payload = job.model_dump_json()
        self._redis.set(self._key(job.job_id), payload, ex=self._ttl_seconds)

    def upsert_job(self, job: AsyncTurnJobResponse) -> None:
        payload = job.model_dump_json()
        self._redis.set(self._key(job.job_id), payload, ex=self._ttl_seconds)

    def get_job(self, job_id: str) -> AsyncTurnJobResponse | None:
        payload = self._redis.get(self._key(job_id))
        if not payload:
            return None
        return AsyncTurnJobResponse.model_validate_json(payload)

    def is_ready(self) -> tuple[bool, str]:
        try:
            self._redis.ping()
            return True, "redis job store ready"
        except Exception as exc:
            return False, f"redis job store not ready: {exc}"


def build_session_store() -> SessionStore:
    backend = settings.session_store_backend.lower()
    if backend == "postgres":
        try:
            return PostgresSessionStore(settings.postgres_dsn)
        except Exception:
            return MemorySessionStore()
    return MemorySessionStore()


def build_job_store() -> JobStore:
    backend = settings.job_store_backend.lower()
    if backend == "redis":
        try:
            return RedisJobStore(redis_url=settings.redis_url, ttl_seconds=settings.async_job_ttl_seconds)
        except Exception:
            return MemoryJobStore()
    return MemoryJobStore()
