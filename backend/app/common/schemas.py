from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Speaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RelationType(str, Enum):
    CAUSAL = "causal"
    CHRONOLOGY = "chronology"
    CONTRAST = "contrast"
    DEPENDENCY = "dependency"
    DEFINITION = "definition"
    EXAMPLE = "example"


class GapType(str, Enum):
    MISSING_PREREQUISITE = "missing_prerequisite"
    WEAK_EVIDENCE = "weak_evidence"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    UNRESOLVED_BRANCH = "unresolved_branch"


class SessionCreateRequest(BaseModel):
    user_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: new_id("sess"))
    tenant_id: str = "public"
    user_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TurnCreateRequest(BaseModel):
    speaker: Speaker
    content: str
    parent_turn_id: str | None = None


class Turn(BaseModel):
    turn_id: str = Field(default_factory=lambda: new_id("turn"))
    tenant_id: str = "public"
    session_id: str
    speaker: Speaker
    content: str
    parent_turn_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Concept(BaseModel):
    node_id: str = Field(default_factory=lambda: new_id("node"))
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    domain: str = "general"
    confidence: float = 0.5
    evidence_turn_ids: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    edge_id: str = Field(default_factory=lambda: new_id("edge"))
    source_node_id: str
    target_node_id: str
    relation_type: RelationType
    confidence: float = 0.5
    evidence_turn_ids: list[str] = Field(default_factory=list)


class Coreference(BaseModel):
    mention: str
    resolved_to: str
    confidence: float = 0.5


class KnowledgeGap(BaseModel):
    gap_id: str = Field(default_factory=lambda: new_id("gap"))
    session_id: str
    gap_type: GapType
    priority: int = 2
    description: str


class ParseTurnRequest(BaseModel):
    tenant_id: str = "public"
    session_id: str
    turn: Turn
    history: list[Turn] = Field(default_factory=list)


class ParseTurnResponse(BaseModel):
    tenant_id: str = "public"
    session_id: str
    turn_id: str
    concepts: list[Concept] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    coreferences: list[Coreference] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)


class GraphUpsertRequest(BaseModel):
    tenant_id: str = "public"
    session_id: str
    concepts: list[Concept] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


class GraphUpsertResponse(BaseModel):
    tenant_id: str = "public"
    session_id: str
    added_nodes: int
    merged_nodes: int
    added_edges: int
    merged_edges: int


class GraphSnapshot(BaseModel):
    tenant_id: str = "public"
    session_id: str
    concepts: list[Concept]
    relations: list[Relation]


class SuggestionRequest(BaseModel):
    tenant_id: str = "public"
    session_id: str
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)


class Suggestion(BaseModel):
    question: str
    reason: str
    priority: int


class SuggestionResponse(BaseModel):
    tenant_id: str = "public"
    session_id: str
    suggestions: list[Suggestion] = Field(default_factory=list)


class DialogueTurnResponse(BaseModel):
    turn: Turn
    parse: ParseTurnResponse
    graph_update: GraphUpsertResponse
    suggested_questions: list[Suggestion] = Field(default_factory=list)


class AsyncJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AsyncTurnAccepted(BaseModel):
    job_id: str
    tenant_id: str
    session_id: str
    turn_id: str
    status: AsyncJobStatus = AsyncJobStatus.QUEUED


class AsyncTurnJobResponse(BaseModel):
    job_id: str
    tenant_id: str
    session_id: str
    turn_id: str
    status: AsyncJobStatus
    result: DialogueTurnResponse | None = None
    error: str | None = None
