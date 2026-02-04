# Backend Services

## Services

- `dialogue-service` (`8101`): session + turn ingestion and orchestration.
- `parser-service` (`8102`): concept/relation/coreference extraction (heuristic or transformer endpoint).
- `graph-service` (`8103`): graph upsert and retrieval (in-memory or Neo4j + Elasticsearch).
- `suggestion-service` (`8104`): follow-up question generation.

## Run with Docker Compose (recommended)

```bash
docker compose up --build
```

App services:
- `http://127.0.0.1:8101` dialogue
- `http://127.0.0.1:8102` parser
- `http://127.0.0.1:8103` graph
- `http://127.0.0.1:8104` suggestion

## Run locally (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run each service in a separate terminal:

```bash
uvicorn app.services.dialogue.main:app --reload --port 8101
uvicorn app.services.parser.main:app --reload --port 8102
uvicorn app.services.graph.main:app --reload --port 8103
uvicorn app.services.suggestion.main:app --reload --port 8104
```

If you run `python3 -m venv` without a target directory, Python will error. Use `python3 -m venv .venv`.

## Example usage

```bash
# 1) create session
curl -s -X POST http://127.0.0.1:8101/v1/sessions \
  -H 'content-type: application/json' \
  -H 'x-tenant-id: public' \
  -d '{"user_id":"demo"}'

# 2) add turn
curl -s -X POST http://127.0.0.1:8101/v1/sessions/<session_id>/turns \
  -H 'content-type: application/json' \
  -H 'x-tenant-id: public' \
  -d '{"speaker":"user","content":"Transformer models improve retrieval because they encode context."}'
```

## Optional production flags

- `AUTH_REQUIRED=true` + `TENANT_API_KEYS_JSON='{"public":"secret"}'` to enforce API-key auth.
- `CONTENT_ENCRYPTION_KEY=<fernet-key>` to encrypt persisted turn content.
- `PARSER_BACKEND=transformer` + `TRANSFORMER_INFERENCE_URL=http://...` for model-backed parsing.
- `GRAPH_BACKEND=neo4j` + Neo4j/Elasticsearch connection env vars for persistent graph/search.
- `ASYNC_PIPELINE_ENABLED=true` + `EVENT_BUS_BACKEND=redis` for queued turn processing:
  - `POST /v1/sessions/{session_id}/turns/async`
  - `GET /v1/pipeline/jobs/{job_id}`
