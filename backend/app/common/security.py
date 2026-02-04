from __future__ import annotations

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app.common.config import settings

try:
    import jwt
except Exception:  # pragma: no cover - optional dependency fallback
    jwt = None  # type: ignore[assignment]


class TenantContext(BaseModel):
    tenant_id: str
    api_key: str | None = None
    subject: str | None = None


def get_tenant_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TenantContext:
    requested_tenant = (x_tenant_id or settings.default_tenant_id).strip()
    if not requested_tenant:
        raise HTTPException(status_code=400, detail="Tenant header cannot be empty")

    mode = settings.auth_mode.strip().lower()
    if settings.auth_required and mode == "none":
        mode = "api_key"

    if mode == "none":
        return TenantContext(tenant_id=requested_tenant, api_key=x_api_key)

    if mode == "api_key":
        expected_key = settings.tenant_api_keys.get(requested_tenant)
        if not expected_key:
            raise HTTPException(status_code=401, detail="Unknown tenant")
        if x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return TenantContext(tenant_id=requested_tenant, api_key=x_api_key)

    if mode == "jwt":
        if jwt is None:
            raise HTTPException(status_code=500, detail="JWT auth mode requires PyJWT dependency")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options={"verify_aud": settings.jwt_audience is not None},
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

        token_tenant = str(payload.get("tenant_id") or payload.get("tid") or payload.get("tenant") or "").strip()
        if token_tenant and requested_tenant and token_tenant != requested_tenant:
            raise HTTPException(status_code=403, detail="Tenant mismatch between token and header")
        resolved_tenant = token_tenant or requested_tenant
        if not resolved_tenant:
            raise HTTPException(status_code=401, detail="Token must include tenant claim")
        return TenantContext(tenant_id=resolved_tenant, subject=str(payload.get("sub", "")) or None)

    raise HTTPException(status_code=500, detail=f"Unsupported auth mode: {mode}")


def ensure_tenant_access(expected_tenant_id: str, context: TenantContext) -> None:
    if expected_tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
