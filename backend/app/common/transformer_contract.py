from __future__ import annotations

from pydantic import BaseModel, Field

from app.common.schemas import GapType, RelationType, Turn


class TransformerConcept(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    domain: str = "general"
    confidence: float = 0.8


class TransformerRelation(BaseModel):
    source: str
    target: str
    relation_type: RelationType = RelationType.DEFINITION
    confidence: float = 0.75


class TransformerCoreference(BaseModel):
    mention: str
    resolved_to: str
    confidence: float = 0.75


class TransformerGap(BaseModel):
    gap_type: GapType
    priority: int = 2
    description: str


class TransformerParseRequest(BaseModel):
    tenant_id: str
    session_id: str
    turn: Turn
    history: list[Turn] = Field(default_factory=list)


class TransformerParseResponse(BaseModel):
    concepts: list[TransformerConcept] = Field(default_factory=list)
    relations: list[TransformerRelation] = Field(default_factory=list)
    coreferences: list[TransformerCoreference] = Field(default_factory=list)
    knowledge_gaps: list[TransformerGap] = Field(default_factory=list)
