from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from app.common.schemas import GapType, Suggestion, SuggestionRequest, SuggestionResponse
from app.common.security import TenantContext, get_tenant_context

app = FastAPI(title="suggestion-service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "suggestion"}


def _gap_to_question(gap_type: GapType, description: str) -> tuple[str, str]:
    if gap_type == GapType.AMBIGUOUS_REFERENCE:
        return (
            "Can you clarify exactly which concept your pronoun refers to?",
            description,
        )
    if gap_type == GapType.MISSING_PREREQUISITE:
        return (
            "What prerequisite concept should we define first before this topic?",
            description,
        )
    if gap_type == GapType.WEAK_EVIDENCE:
        return (
            "What evidence or source best supports this relationship?",
            description,
        )
    return (
        "Which branch should we expand next to make this knowledge path complete?",
        description,
    )


@app.post("/v1/suggestions/questions", response_model=SuggestionResponse)
def suggest_questions(
    payload: SuggestionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> SuggestionResponse:
    if payload.tenant_id and payload.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch in suggestion payload")

    ranked: list[Suggestion] = []
    for gap in sorted(payload.knowledge_gaps, key=lambda g: g.priority, reverse=True):
        q, reason = _gap_to_question(gap.gap_type, gap.description)
        ranked.append(Suggestion(question=q, reason=reason, priority=gap.priority))

    if not ranked:
        ranked.append(
            Suggestion(
                question="Would you like to add examples, counterpoints, or prerequisites to this topic?",
                reason="No high-priority gaps were detected.",
                priority=1,
            )
        )

    return SuggestionResponse(tenant_id=tenant.tenant_id, session_id=payload.session_id, suggestions=ranked)
