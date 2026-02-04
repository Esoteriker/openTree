from __future__ import annotations

from typing import Any

import httpx


def check_http_health(url: str, timeout_seconds: float = 1.0) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
        if 200 <= response.status_code < 300:
            return True, f"{url} healthy"
        return False, f"{url} unhealthy status={response.status_code}"
    except Exception as exc:
        return False, f"{url} unreachable: {exc}"


def summarize_checks(checks: dict[str, tuple[bool, str]]) -> dict[str, Any]:
    ready = all(result[0] for result in checks.values())
    details = {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()}
    return {"ready": ready, "checks": details}
