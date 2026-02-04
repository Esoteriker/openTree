#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


def _request(method: str, url: str, payload: dict | None = None) -> dict:
    body = None
    headers = {"Content-Type": "application/json", "X-Tenant-ID": os.getenv("TENANT_ID", "public")}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:  # noqa: S310 - local dev URLs only
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} failed status={exc.code} body={exc.read().decode('utf-8')}") from exc


def main() -> None:
    dialogue_url = os.getenv("DIALOGUE_URL", "http://127.0.0.1:8101")
    ready = _request("GET", f"{dialogue_url}/ready")
    if not ready.get("ready"):
        raise RuntimeError(f"dialogue service not ready: {ready}")

    session = _request("POST", f"{dialogue_url}/v1/sessions", {"user_id": "smoke"})
    session_id = session["session_id"]

    sync_result = _request(
        "POST",
        f"{dialogue_url}/v1/sessions/{session_id}/turns",
        {
            "speaker": "user",
            "content": "Transformer models improve retrieval because they encode context.",
        },
    )
    if "parse" not in sync_result or "graph_update" not in sync_result:
        raise RuntimeError(f"unexpected sync response: {sync_result}")

    accepted = _request(
        "POST",
        f"{dialogue_url}/v1/sessions/{session_id}/turns/async",
        {
            "speaker": "user",
            "content": "It also helps disambiguate references.",
        },
    )
    job_id = accepted["job_id"]

    job = {}
    for _ in range(25):
        job = _request("GET", f"{dialogue_url}/v1/pipeline/jobs/{job_id}")
        if job.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.2)

    if job.get("status") != "completed":
        raise RuntimeError(f"async job did not complete: {job}")

    graph = _request("GET", f"{dialogue_url}/v1/sessions/{session_id}/graph")
    if "concepts" not in graph:
        raise RuntimeError(f"unexpected graph response: {graph}")

    print("Smoke test passed")


if __name__ == "__main__":
    main()
