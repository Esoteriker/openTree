from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import Depends, FastAPI, HTTPException

from app.common.config import settings
from app.common.observability import install_request_metrics_middleware
from app.common.readiness import check_http_health, summarize_checks
from app.common.schemas import ParseTurnRequest, ParseTurnResponse
from app.common.security import TenantContext, get_tenant_context
from app.services.parser.backends import build_parser_backend

app = FastAPI(title="parser-service", version="0.2.0")
install_request_metrics_middleware(app)

PARSER_BACKEND = build_parser_backend()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "parser", "backend": settings.parser_backend}


@app.get("/ready")
def ready() -> dict[str, object]:
    checks: dict[str, tuple[bool, str]] = {}
    if settings.parser_backend.lower() == "transformer":
        if settings.transformer_inference_url:
            checks["transformer_backend"] = check_http_health(_transformer_health_url())
        else:
            checks["transformer_backend"] = (False, "TRANSFORMER_INFERENCE_URL is required for transformer backend")
    else:
        checks["heuristic_backend"] = (True, "heuristic backend ready")
    return summarize_checks(checks)


@app.post("/v1/parse/turn", response_model=ParseTurnResponse)
def parse_turn(
    payload: ParseTurnRequest,
    tenant: TenantContext = Depends(get_tenant_context),
) -> ParseTurnResponse:
    if payload.tenant_id and payload.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch in parse payload")
    normalized = payload.model_copy(update={"tenant_id": tenant.tenant_id})
    return PARSER_BACKEND.parse_turn(normalized)


def _transformer_health_url() -> str:
    split = urlsplit(settings.transformer_inference_url or "")
    if not split.scheme or not split.netloc:
        return settings.transformer_inference_url or ""
    return urlunsplit((split.scheme, split.netloc, "/health", "", ""))
