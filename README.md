# OpenTree

AI dialogue-based knowledge structuring and management scaffold.

This repository bootstraps a v1 platform that converts chat turns into a tree/graph of concepts, relations, evidence, and knowledge gaps.

## What is included

- `docs/v1-system-design.md`: architecture, API contracts, and event flow.
- `backend/`: FastAPI microservice scaffold:
  - `dialogue-service`: session and turn ingestion, context chain tracking.
  - `parser-service`: concept/relation/coreference extraction (heuristic baseline).
  - `graph-service`: knowledge graph upsert and retrieval API (in-memory placeholder).
  - `suggestion-service`: knowledge-gap driven follow-up question generation.
- `frontend/`: UI shell + extension scaffolds:
  - Web Components knowledge tree editor starter.
  - Browser extension starter (WebExtension manifest + content script).
  - VS Code extension starter (command and webview entrypoint).

## Quick start

### 1. Backend (Option A: Docker Compose)

```bash
cd backend
docker compose up --build
```

This starts:
- app services on `8101`-`8104`
- infra services (Neo4j, Elasticsearch, Postgres, Redis)

### 2. Backend (Option B: local Python)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run services in separate terminals:

```bash
# terminal 1
uvicorn app.services.dialogue.main:app --reload --port 8101

# terminal 2
uvicorn app.services.parser.main:app --reload --port 8102

# terminal 3
uvicorn app.services.graph.main:app --reload --port 8103

# terminal 4
uvicorn app.services.suggestion.main:app --reload --port 8104
```

Note: `python3 -m venv` requires a directory argument. Use `python3 -m venv .venv`.

### 3. Frontend UI shell

Run a local static server:

```bash
cd frontend/packages/ui-shell
python3 -m http.server 4173
```

Then open `http://127.0.0.1:4173` to use the MVP UI:
- create a session
- send turns
- view live graph + follow-up suggestions

## Next implementation milestones

1. Replace parser heuristics with a fine-tuned transformer model. (Added transformer inference backend path with fallback.)
2. Replace in-memory graph stores with Neo4j + Elasticsearch integrations. (Added repository switch with Neo4j/ES backend.)
3. Add async event bus (Redis Streams/Kafka) for production-grade throughput. (Added Redis Streams + async job endpoints.)
4. Add auth, tenant isolation, and encrypted data pipelines. (Added tenant headers/API key auth option + encrypted turn storage.)
