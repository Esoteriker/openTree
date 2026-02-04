# Transformer Inference Contract

`parser-service` expects `TRANSFORMER_INFERENCE_URL` to implement:

- `POST /v1/infer/parse-turn`
- Request and response schemas are defined in `backend/app/common/transformer_contract.py`.

## Request shape

```json
{
  "tenant_id": "public",
  "session_id": "sess_123",
  "turn": {
    "turn_id": "turn_123",
    "tenant_id": "public",
    "session_id": "sess_123",
    "speaker": "user",
    "content": "Transformers improve retrieval because they encode context.",
    "parent_turn_id": null,
    "created_at": "2026-02-04T00:00:00Z"
  },
  "history": []
}
```

## Response shape

```json
{
  "concepts": [
    {
      "canonical_name": "Transformers",
      "aliases": ["Transformer models"],
      "domain": "nlp",
      "confidence": 0.92
    }
  ],
  "relations": [
    {
      "source": "Transformers",
      "target": "retrieval",
      "relation_type": "causal",
      "confidence": 0.88
    }
  ],
  "coreferences": [
    {
      "mention": "it",
      "resolved_to": "Transformers",
      "confidence": 0.81
    }
  ],
  "knowledge_gaps": [
    {
      "gap_type": "weak_evidence",
      "priority": 2,
      "description": "Need stronger citation for causal relation."
    }
  ]
}
```

## Local mock provider

For local and CI runs, this repository includes:

- `mock-transformer-service`: `backend/app/services/model_inference/main.py`

In Docker Compose it runs on `http://127.0.0.1:8110`.
