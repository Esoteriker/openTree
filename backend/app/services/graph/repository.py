from __future__ import annotations

from collections import defaultdict

from app.common.config import settings
from app.common.schemas import Concept, GraphSnapshot, GraphUpsertRequest, GraphUpsertResponse, Relation, RelationType

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency fallback
    GraphDatabase = None  # type: ignore[assignment]

try:
    from elasticsearch import Elasticsearch
except Exception:  # pragma: no cover - optional dependency fallback
    Elasticsearch = None  # type: ignore[assignment]


class GraphRepository:
    def upsert(self, payload: GraphUpsertRequest) -> GraphUpsertResponse:
        raise NotImplementedError

    def get_snapshot(self, tenant_id: str, session_id: str) -> GraphSnapshot | None:
        raise NotImplementedError

    def is_ready(self) -> tuple[bool, str]:
        raise NotImplementedError


class MemoryGraphRepository(GraphRepository):
    def __init__(self) -> None:
        self.concepts_by_scope: dict[str, dict[str, Concept]] = defaultdict(dict)
        self.relations_by_scope: dict[str, dict[tuple[str, str, str], Relation]] = defaultdict(dict)

    def _scope_key(self, tenant_id: str, session_id: str) -> str:
        return f"{tenant_id}:{session_id}"

    def upsert(self, payload: GraphUpsertRequest) -> GraphUpsertResponse:
        scope_key = self._scope_key(payload.tenant_id, payload.session_id)
        session_concepts = self.concepts_by_scope[scope_key]
        session_relations = self.relations_by_scope[scope_key]

        id_map: dict[str, str] = {}
        added_nodes = 0
        merged_nodes = 0
        for concept in payload.concepts:
            key = concept.canonical_name.strip().lower()
            existing = session_concepts.get(key)
            if existing:
                merged_nodes += 1
                existing.aliases = sorted(set(existing.aliases + concept.aliases))
                existing.evidence_turn_ids = sorted(set(existing.evidence_turn_ids + concept.evidence_turn_ids))
                existing.confidence = max(existing.confidence, concept.confidence)
                id_map[concept.node_id] = existing.node_id
            else:
                added_nodes += 1
                session_concepts[key] = concept
                id_map[concept.node_id] = concept.node_id

        added_edges = 0
        merged_edges = 0
        for relation in payload.relations:
            src_id = id_map.get(relation.source_node_id)
            dst_id = id_map.get(relation.target_node_id)
            if not src_id or not dst_id:
                continue

            relation.source_node_id = src_id
            relation.target_node_id = dst_id
            dedup_key = (src_id, dst_id, relation.relation_type.value)
            existing_relation = session_relations.get(dedup_key)
            if existing_relation:
                merged_edges += 1
                existing_relation.confidence = max(existing_relation.confidence, relation.confidence)
                existing_relation.evidence_turn_ids = sorted(
                    set(existing_relation.evidence_turn_ids + relation.evidence_turn_ids)
                )
            else:
                added_edges += 1
                session_relations[dedup_key] = relation

        return GraphUpsertResponse(
            tenant_id=payload.tenant_id,
            session_id=payload.session_id,
            added_nodes=added_nodes,
            merged_nodes=merged_nodes,
            added_edges=added_edges,
            merged_edges=merged_edges,
        )

    def get_snapshot(self, tenant_id: str, session_id: str) -> GraphSnapshot | None:
        scope_key = self._scope_key(tenant_id, session_id)
        if scope_key not in self.concepts_by_scope:
            return None
        concepts = list(self.concepts_by_scope[scope_key].values())
        relations = list(self.relations_by_scope[scope_key].values())
        return GraphSnapshot(tenant_id=tenant_id, session_id=session_id, concepts=concepts, relations=relations)

    def is_ready(self) -> tuple[bool, str]:
        return True, "memory graph repository ready"


class Neo4jElasticsearchRepository(GraphRepository):
    def __init__(self) -> None:
        if GraphDatabase is None:
            raise RuntimeError("neo4j package is required for Neo4j graph backend")
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        self.elasticsearch = Elasticsearch(settings.elasticsearch_url) if Elasticsearch else None
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        if not self.elasticsearch:
            return
        try:
            if not self.elasticsearch.indices.exists(index=settings.elasticsearch_index_name):
                self.elasticsearch.indices.create(
                    index=settings.elasticsearch_index_name,
                    mappings={
                        "properties": {
                            "tenant_id": {"type": "keyword"},
                            "session_id": {"type": "keyword"},
                            "entity_type": {"type": "keyword"},
                            "entity_id": {"type": "keyword"},
                            "text": {"type": "text"},
                            "evidence_turn_ids": {"type": "keyword"},
                        }
                    },
                )
        except Exception:
            return

    def upsert(self, payload: GraphUpsertRequest) -> GraphUpsertResponse:
        added_nodes = 0
        merged_nodes = 0
        added_edges = 0
        merged_edges = 0
        id_map: dict[str, str] = {}

        with self.driver.session() as session:
            for concept in payload.concepts:
                existing = session.run(
                    """
                    MATCH (c:Concept {tenant_id: $tenant_id, session_id: $session_id, canonical_name: $canonical_name})
                    RETURN c.node_id AS node_id, c.aliases AS aliases, c.evidence_turn_ids AS evidence_turn_ids, c.confidence AS confidence
                    """,
                    tenant_id=payload.tenant_id,
                    session_id=payload.session_id,
                    canonical_name=concept.canonical_name,
                ).single()

                if existing:
                    merged_nodes += 1
                    canonical_id = existing["node_id"]
                    aliases = sorted(set((existing["aliases"] or []) + concept.aliases))
                    evidence_turn_ids = sorted(
                        set((existing["evidence_turn_ids"] or []) + concept.evidence_turn_ids)
                    )
                    confidence = max(float(existing["confidence"] or 0.0), concept.confidence)
                    session.run(
                        """
                        MATCH (c:Concept {tenant_id: $tenant_id, session_id: $session_id, canonical_name: $canonical_name})
                        SET c.aliases = $aliases,
                            c.evidence_turn_ids = $evidence_turn_ids,
                            c.confidence = $confidence
                        """,
                        tenant_id=payload.tenant_id,
                        session_id=payload.session_id,
                        canonical_name=concept.canonical_name,
                        aliases=aliases,
                        evidence_turn_ids=evidence_turn_ids,
                        confidence=confidence,
                    )
                else:
                    added_nodes += 1
                    canonical_id = concept.node_id
                    session.run(
                        """
                        CREATE (c:Concept {
                            node_id: $node_id,
                            tenant_id: $tenant_id,
                            session_id: $session_id,
                            canonical_name: $canonical_name,
                            aliases: $aliases,
                            domain: $domain,
                            confidence: $confidence,
                            evidence_turn_ids: $evidence_turn_ids
                        })
                        """,
                        node_id=concept.node_id,
                        tenant_id=payload.tenant_id,
                        session_id=payload.session_id,
                        canonical_name=concept.canonical_name,
                        aliases=concept.aliases,
                        domain=concept.domain,
                        confidence=concept.confidence,
                        evidence_turn_ids=concept.evidence_turn_ids,
                    )

                id_map[concept.node_id] = canonical_id
                self._index_concept(payload.tenant_id, payload.session_id, concept, canonical_id)

            for relation in payload.relations:
                src_id = id_map.get(relation.source_node_id)
                dst_id = id_map.get(relation.target_node_id)
                if not src_id or not dst_id:
                    continue

                existing = session.run(
                    """
                    MATCH (src:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $src_id})
                          -[r:RELATION {tenant_id: $tenant_id, session_id: $session_id, relation_type: $relation_type}]->
                          (dst:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $dst_id})
                    RETURN r.edge_id AS edge_id, r.confidence AS confidence, r.evidence_turn_ids AS evidence_turn_ids
                    """,
                    tenant_id=payload.tenant_id,
                    session_id=payload.session_id,
                    src_id=src_id,
                    dst_id=dst_id,
                    relation_type=relation.relation_type.value,
                ).single()

                if existing:
                    merged_edges += 1
                    edge_id = existing["edge_id"]
                    confidence = max(float(existing["confidence"] or 0.0), relation.confidence)
                    evidence_turn_ids = sorted(
                        set((existing["evidence_turn_ids"] or []) + relation.evidence_turn_ids)
                    )
                    session.run(
                        """
                        MATCH (src:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $src_id})
                              -[r:RELATION {tenant_id: $tenant_id, session_id: $session_id, relation_type: $relation_type}]->
                              (dst:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $dst_id})
                        SET r.confidence = $confidence,
                            r.evidence_turn_ids = $evidence_turn_ids
                        """,
                        tenant_id=payload.tenant_id,
                        session_id=payload.session_id,
                        src_id=src_id,
                        dst_id=dst_id,
                        relation_type=relation.relation_type.value,
                        confidence=confidence,
                        evidence_turn_ids=evidence_turn_ids,
                    )
                else:
                    added_edges += 1
                    edge_id = relation.edge_id
                    session.run(
                        """
                        MATCH (src:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $src_id})
                        MATCH (dst:Concept {tenant_id: $tenant_id, session_id: $session_id, node_id: $dst_id})
                        CREATE (src)-[:RELATION {
                            edge_id: $edge_id,
                            tenant_id: $tenant_id,
                            session_id: $session_id,
                            relation_type: $relation_type,
                            confidence: $confidence,
                            evidence_turn_ids: $evidence_turn_ids
                        }]->(dst)
                        """,
                        edge_id=edge_id,
                        tenant_id=payload.tenant_id,
                        session_id=payload.session_id,
                        src_id=src_id,
                        dst_id=dst_id,
                        relation_type=relation.relation_type.value,
                        confidence=relation.confidence,
                        evidence_turn_ids=relation.evidence_turn_ids,
                    )

                relation.source_node_id = src_id
                relation.target_node_id = dst_id
                self._index_relation(payload.tenant_id, payload.session_id, relation, edge_id)

        return GraphUpsertResponse(
            tenant_id=payload.tenant_id,
            session_id=payload.session_id,
            added_nodes=added_nodes,
            merged_nodes=merged_nodes,
            added_edges=added_edges,
            merged_edges=merged_edges,
        )

    def get_snapshot(self, tenant_id: str, session_id: str) -> GraphSnapshot | None:
        concepts: list[Concept] = []
        relations: list[Relation] = []

        with self.driver.session() as session:
            concept_rows = session.run(
                """
                MATCH (c:Concept {tenant_id: $tenant_id, session_id: $session_id})
                RETURN c.node_id AS node_id,
                       c.canonical_name AS canonical_name,
                       c.aliases AS aliases,
                       c.domain AS domain,
                       c.confidence AS confidence,
                       c.evidence_turn_ids AS evidence_turn_ids
                """,
                tenant_id=tenant_id,
                session_id=session_id,
            )
            for row in concept_rows:
                concepts.append(
                    Concept(
                        node_id=row["node_id"],
                        canonical_name=row["canonical_name"],
                        aliases=row["aliases"] or [],
                        domain=row["domain"] or "general",
                        confidence=float(row["confidence"] or 0.5),
                        evidence_turn_ids=row["evidence_turn_ids"] or [],
                    )
                )

            relation_rows = session.run(
                """
                MATCH (src:Concept {tenant_id: $tenant_id, session_id: $session_id})
                      -[r:RELATION {tenant_id: $tenant_id, session_id: $session_id}]->
                      (dst:Concept {tenant_id: $tenant_id, session_id: $session_id})
                RETURN r.edge_id AS edge_id,
                       src.node_id AS source_node_id,
                       dst.node_id AS target_node_id,
                       r.relation_type AS relation_type,
                       r.confidence AS confidence,
                       r.evidence_turn_ids AS evidence_turn_ids
                """,
                tenant_id=tenant_id,
                session_id=session_id,
            )
            for row in relation_rows:
                relation_type_name = row["relation_type"] or RelationType.DEFINITION.value
                try:
                    relation_type = RelationType(relation_type_name)
                except ValueError:
                    relation_type = RelationType.DEFINITION
                relations.append(
                    Relation(
                        edge_id=row["edge_id"],
                        source_node_id=row["source_node_id"],
                        target_node_id=row["target_node_id"],
                        relation_type=relation_type,
                        confidence=float(row["confidence"] or 0.5),
                        evidence_turn_ids=row["evidence_turn_ids"] or [],
                    )
                )

        if not concepts and not relations:
            return None

        return GraphSnapshot(tenant_id=tenant_id, session_id=session_id, concepts=concepts, relations=relations)

    def _index_concept(self, tenant_id: str, session_id: str, concept: Concept, canonical_id: str) -> None:
        if not self.elasticsearch:
            return
        try:
            self.elasticsearch.index(
                index=settings.elasticsearch_index_name,
                id=f"{tenant_id}:{session_id}:concept:{canonical_id}",
                document={
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "entity_type": "concept",
                    "entity_id": canonical_id,
                    "text": concept.canonical_name,
                    "evidence_turn_ids": concept.evidence_turn_ids,
                },
            )
        except Exception:
            return

    def _index_relation(self, tenant_id: str, session_id: str, relation: Relation, edge_id: str) -> None:
        if not self.elasticsearch:
            return
        try:
            self.elasticsearch.index(
                index=settings.elasticsearch_index_name,
                id=f"{tenant_id}:{session_id}:relation:{edge_id}",
                document={
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "entity_type": "relation",
                    "entity_id": edge_id,
                    "text": f"{relation.source_node_id} {relation.relation_type.value} {relation.target_node_id}",
                    "evidence_turn_ids": relation.evidence_turn_ids,
                },
            )
        except Exception:
            return

    def is_ready(self) -> tuple[bool, str]:
        try:
            with self.driver.session() as session:
                session.run("RETURN 1").single()
            if self.elasticsearch:
                self.elasticsearch.ping()
            return True, "neo4j/elasticsearch graph repository ready"
        except Exception as exc:
            return False, f"graph repository not ready: {exc}"


def build_graph_repository() -> GraphRepository:
    backend = settings.graph_backend.lower()
    if backend == "neo4j":
        try:
            return Neo4jElasticsearchRepository()
        except Exception:
            return MemoryGraphRepository()
    return MemoryGraphRepository()
