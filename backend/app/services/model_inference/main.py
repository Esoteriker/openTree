from __future__ import annotations

import re

from fastapi import FastAPI

from app.common.schemas import GapType, RelationType
from app.common.transformer_contract import (
    TransformerConcept,
    TransformerCoreference,
    TransformerGap,
    TransformerParseRequest,
    TransformerParseResponse,
    TransformerRelation,
)

app = FastAPI(title="mock-transformer-service", version="0.1.0")

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{3,}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock-transformer"}


@app.post("/v1/infer/parse-turn", response_model=TransformerParseResponse)
def parse_turn(payload: TransformerParseRequest) -> TransformerParseResponse:
    text = payload.turn.content
    tokens = TOKEN_PATTERN.findall(text)
    concepts: list[TransformerConcept] = []
    seen: set[str] = set()
    for token in tokens[:8]:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        concepts.append(TransformerConcept(canonical_name=token, confidence=0.84))

    relations: list[TransformerRelation] = []
    if len(concepts) >= 2:
        relation_type = RelationType.DEFINITION
        low = text.lower()
        if "because" in low or "causes" in low or "leads to" in low:
            relation_type = RelationType.CAUSAL
        relations.append(
            TransformerRelation(
                source=concepts[0].canonical_name,
                target=concepts[1].canonical_name,
                relation_type=relation_type,
                confidence=0.79,
            )
        )

    coreferences: list[TransformerCoreference] = []
    low = text.lower()
    if " it " in f" {low} " and payload.history:
        history_text = payload.history[-1].content.split()
        antecedent = history_text[-1] if history_text else "previous concept"
        coreferences.append(TransformerCoreference(mention="it", resolved_to=antecedent, confidence=0.76))

    gaps: list[TransformerGap] = []
    if "?" in text and len(concepts) <= 1:
        gaps.append(
            TransformerGap(
                gap_type=GapType.MISSING_PREREQUISITE,
                priority=2,
                description="Question is underspecified for extraction model.",
            )
        )

    return TransformerParseResponse(
        concepts=concepts,
        relations=relations,
        coreferences=coreferences,
        knowledge_gaps=gaps,
    )
