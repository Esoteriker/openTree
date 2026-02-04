from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from app.common.schemas import GraphSnapshot, GraphUpsertRequest, GraphUpsertResponse
from app.common.security import TenantContext, get_tenant_context
from app.services.graph.repository import build_graph_repository

app = FastAPI(title="graph-service", version="0.2.0")

GRAPH_REPOSITORY = build_graph_repository()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "graph"}


@app.post("/v1/graph/upsert", response_model=GraphUpsertResponse)
def upsert_graph(
    payload: GraphUpsertRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> GraphUpsertResponse:
    if payload.tenant_id and payload.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch in graph upsert payload")

    normalized = payload.model_copy(update={"tenant_id": tenant.tenant_id})
    return GRAPH_REPOSITORY.upsert(normalized)


@app.get("/v1/graph/{session_id}", response_model=GraphSnapshot)
def get_graph(
    session_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> GraphSnapshot:
    snapshot = GRAPH_REPOSITORY.get_snapshot(tenant_id=tenant.tenant_id, session_id=session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Session graph not found")
    return snapshot
