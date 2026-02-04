from __future__ import annotations

from fastapi.testclient import TestClient

from app.common.transformer_contract import TransformerParseResponse
from app.services.model_inference.main import app


def test_mock_transformer_respects_contract() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/infer/parse-turn",
        json={
            "tenant_id": "public",
            "session_id": "sess_demo",
            "turn": {
                "turn_id": "turn_1",
                "tenant_id": "public",
                "session_id": "sess_demo",
                "speaker": "user",
                "content": "Transformers improve search because they encode context.",
                "parent_turn_id": None,
                "created_at": "2026-01-01T00:00:00Z",
            },
            "history": [],
        },
    )

    assert response.status_code == 200
    parsed = TransformerParseResponse.model_validate(response.json())
    assert parsed.concepts
