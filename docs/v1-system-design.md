# V1 System Design

## 1. Goals and scope

V1 focuses on the core loop:

1. Ingest AI dialogue turns.
2. Parse concepts/relations/coreferences.
3. Update a knowledge tree/graph with evidence links.
4. Generate follow-up questions from knowledge gaps.
5. Let users correct structure through UI interactions.

Target latency for sync user path is <200ms using lightweight extraction, async deep inference.

## 2. High-level architecture

### 2.1 Frontend surfaces

- Browser extension (`WebExtension`) to capture chat content from AI web apps.
- VS Code extension to capture editor-side AI interactions.
- Shared Web Components UI shell for tree editing and annotation.

### 2.2 Backend microservices

- `dialogue-service`: session lifecycle, turn normalization, context chain tracking.
- `parser-service`: NLP extraction for concepts, relations, coreference candidates.
- `graph-service`: write/read concept nodes and relationship edges.
- `suggestion-service`: identify knowledge gaps and generate follow-up prompts.

### 2.3 Data backends (production target)

- Graph DB: Neo4j for relationships and traversals.
- Search index: Elasticsearch/OpenSearch for evidence and semantic lookup.
- Relational metadata: PostgreSQL for tenants, sessions, audit logs.
- Cache/queue: Redis (MVP), Kafka (scale-out phase).

## 3. Core data model

### 3.1 Entities

- `ConversationSession`
  - `session_id`
  - `user_id`
  - `created_at`
  - `metadata`
- `Turn`
  - `turn_id`
  - `session_id`
  - `speaker` (`user` | `assistant` | `system`)
  - `content`
  - `parent_turn_id` (for chain/path)
  - `created_at`
- `ConceptNode`
  - `node_id`
  - `canonical_name`
  - `aliases[]`
  - `domain`
  - `confidence`
- `RelationEdge`
  - `edge_id`
  - `source_node_id`
  - `target_node_id`
  - `relation_type` (`causal`, `chronology`, `contrast`, `dependency`, `definition`, `example`)
  - `confidence`
  - `evidence_turn_ids[]`
- `KnowledgeGap`
  - `gap_id`
  - `session_id`
  - `gap_type` (`missing_prerequisite`, `weak_evidence`, `ambiguous_reference`, `unresolved_branch`)
  - `priority`
  - `description`
  - `suggested_questions[]`

## 4. API contracts (v1)

### 4.1 dialogue-service

- `POST /v1/sessions`
  - Request: `{ "user_id": "u_123", "metadata": {...} }`
  - Response: `{ "session_id": "...", "created_at": "..." }`
- `POST /v1/sessions/{session_id}/turns`
  - Request: `{ "speaker": "user", "content": "...", "parent_turn_id": "..." }`
  - Response: `{ "turn": {...}, "parse": {...}, "graph_update": {...}, "gaps": [...], "suggested_questions": [...] }`

### 4.2 parser-service

- `POST /v1/parse/turn`
  - Request: `{ "session_id": "...", "turn": {...}, "history": [...] }`
  - Response:
    - `concepts[]`
    - `relations[]`
    - `coreferences[]`
    - `knowledge_gaps[]`

### 4.3 graph-service

- `POST /v1/graph/upsert`
  - Request: parse output payload.
  - Response: merge stats, changed nodes/edges.
- `GET /v1/graph/{session_id}`
  - Response: graph snapshot for UI rendering.

### 4.4 suggestion-service

- `POST /v1/suggestions/questions`
  - Request: `knowledge_gaps[]`
  - Response: ranked follow-up prompts.

## 5. Event flow

1. User sends chat message.
2. Extension/SDK posts turn to `dialogue-service`.
3. `dialogue-service` calls `parser-service` with turn + local context chain.
4. Parser returns concepts, relations, coreference links, and candidate gaps.
5. `dialogue-service` sends extracted structures to `graph-service`.
6. Graph updates and returns merge/change summary.
7. `dialogue-service` sends gaps to `suggestion-service` for follow-up prompts.
8. Response returns to client with updated graph delta + suggested questions.

### 5.1 Async pipeline mode

- Optional endpoint: `POST /v1/sessions/{session_id}/turns/async`.
- Dialogue service publishes `turn.ingested` to event bus (`inmemory` or Redis Streams).
- Worker consumes events, runs parser/graph/suggestion pipeline, stores job result.
- Worker retries transient failures with exponential backoff.
- Failed events are written to `turn.dead_letter` for triage.
- Client polls `GET /v1/pipeline/jobs/{job_id}` for completion state.

## 6. Performance strategy

- Sync path budget:
  - turn normalization: 15-20ms
  - lightweight extraction: 50-70ms
  - graph delta write: 40-60ms
  - suggestion generation: 20-30ms
- Async path:
  - deeper relation inference (GNN), re-ranking, and cross-session dedup.

## 7. Security and compliance baseline

- Tenant-scoped IDs and row-level filters.
- PII-aware content redaction hooks before persistence.
- Encryption at rest for all persisted conversation and graph metadata.
- Audit logs for node/edge edits and suggestion acceptance.
- Auth modes: `none`, `api_key`, `jwt` (tenant claim enforced).

## 8. Reliability and operations

- `GET /health` + `GET /ready` for liveliness and dependency readiness.
- Request-id and latency middleware for all services.
- Persistent stores:
  - sessions/turns: PostgreSQL (`SESSION_STORE_BACKEND=postgres`)
  - async jobs: Redis (`JOB_STORE_BACKEND=redis`)

## 9. Near-term implementation roadmap

1. MVP: in-memory graph + heuristic parser + manual correction UI.
2. Beta: Neo4j integration + embedding index + auth/teams.
3. GA: domain-adapted extraction model, feedback training loop, enterprise controls.
