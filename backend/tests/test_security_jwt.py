from __future__ import annotations

import jwt
import pytest
from fastapi import HTTPException

from app.common.config import settings
from app.common.security import get_tenant_context


def test_jwt_auth_resolves_tenant_and_subject() -> None:
    old_mode = settings.auth_mode
    old_secret = settings.jwt_secret
    old_audience = settings.jwt_audience
    old_issuer = settings.jwt_issuer
    try:
        settings.auth_mode = "jwt"
        settings.jwt_secret = "unit-test-secret"
        settings.jwt_audience = None
        settings.jwt_issuer = None
        token = jwt.encode({"sub": "u_1", "tenant_id": "acme"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        ctx = get_tenant_context(x_tenant_id="acme", x_api_key=None, authorization=f"Bearer {token}")

        assert ctx.tenant_id == "acme"
        assert ctx.subject == "u_1"
    finally:
        settings.auth_mode = old_mode
        settings.jwt_secret = old_secret
        settings.jwt_audience = old_audience
        settings.jwt_issuer = old_issuer


def test_jwt_auth_rejects_header_mismatch() -> None:
    old_mode = settings.auth_mode
    old_secret = settings.jwt_secret
    old_audience = settings.jwt_audience
    old_issuer = settings.jwt_issuer
    try:
        settings.auth_mode = "jwt"
        settings.jwt_secret = "unit-test-secret"
        settings.jwt_audience = None
        settings.jwt_issuer = None
        token = jwt.encode({"sub": "u_1", "tenant_id": "acme"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        with pytest.raises(HTTPException):
            get_tenant_context(x_tenant_id="other", x_api_key=None, authorization=f"Bearer {token}")
    finally:
        settings.auth_mode = old_mode
        settings.jwt_secret = old_secret
        settings.jwt_audience = old_audience
        settings.jwt_issuer = old_issuer
