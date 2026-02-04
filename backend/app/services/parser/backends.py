from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import httpx

from app.common.config import settings
from app.common.schemas import (
    Concept,
    Coreference,
    GapType,
    KnowledgeGap,
    ParseTurnRequest,
    ParseTurnResponse,
    Relation,
    RelationType,
)
from app.common.transformer_contract import TransformerParseRequest, TransformerParseResponse

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
PHRASE_PATTERN = re.compile(r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)")


class ParserBackend:
    def parse_turn(self, payload: ParseTurnRequest) -> ParseTurnResponse:
        raise NotImplementedError


class HeuristicParserBackend(ParserBackend):
    def __init__(self) -> None:
        self.session_concept_memory: dict[str, list[str]] = defaultdict(list)

    def _memory_key(self, tenant_id: str, session_id: str) -> str:
        return f"{tenant_id}:{session_id}"

    def _extract_concepts(self, text: str, turn_id: str) -> list[Concept]:
        concepts: list[Concept] = []
        seen: set[str] = set()

        for phrase in PHRASE_PATTERN.findall(text):
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            concepts.append(
                Concept(
                    canonical_name=phrase,
                    confidence=0.72,
                    evidence_turn_ids=[turn_id],
                )
            )

        for token in TOKEN_PATTERN.findall(text):
            low = token.lower()
            if low in seen or low in {"what", "when", "where", "which", "with", "that", "this", "from", "into"}:
                continue
            if len(low) < 5:
                continue
            seen.add(low)
            concepts.append(
                Concept(
                    canonical_name=token,
                    confidence=0.58,
                    evidence_turn_ids=[turn_id],
                )
            )

        return concepts

    def _extract_relations(self, text: str, concepts: list[Concept], turn_id: str) -> list[Relation]:
        if len(concepts) < 2:
            return []

        relation_type = None
        text_low = text.lower()
        if "because" in text_low or "leads to" in text_low or "causes" in text_low:
            relation_type = RelationType.CAUSAL
        elif "before" in text_low or "after" in text_low or "then" in text_low:
            relation_type = RelationType.CHRONOLOGY
        elif "however" in text_low or "while" in text_low or "in contrast" in text_low:
            relation_type = RelationType.CONTRAST
        elif "depends on" in text_low or "require" in text_low:
            relation_type = RelationType.DEPENDENCY
        elif "is" in text_low or "means" in text_low:
            relation_type = RelationType.DEFINITION

        if relation_type is None:
            return []

        src = concepts[0]
        dst = concepts[1]
        return [
            Relation(
                source_node_id=src.node_id,
                target_node_id=dst.node_id,
                relation_type=relation_type,
                confidence=0.6,
                evidence_turn_ids=[turn_id],
            )
        ]

    def _resolve_coreference(self, tenant_id: str, session_id: str, text: str) -> list[Coreference]:
        matches = []
        mention_hits = re.findall(r"\b(this|that|it|they|these|those)\b", text.lower())
        if not mention_hits:
            return matches

        memory = self.session_concept_memory.get(self._memory_key(tenant_id, session_id), [])
        if not memory:
            return matches

        antecedent = memory[-1]
        for mention in mention_hits:
            matches.append(Coreference(mention=mention, resolved_to=antecedent, confidence=0.67))
        return matches

    def _build_gaps(
        self,
        session_id: str,
        text: str,
        concepts: list[Concept],
        coreferences: list[Coreference],
    ) -> list[KnowledgeGap]:
        gaps: list[KnowledgeGap] = []

        if re.search(r"\b(this|that|it|they|these|those)\b", text.lower()) and not coreferences:
            gaps.append(
                KnowledgeGap(
                    session_id=session_id,
                    gap_type=GapType.AMBIGUOUS_REFERENCE,
                    priority=3,
                    description="Pronoun reference is unresolved in current context.",
                )
            )

        if "?" in text and len(concepts) <= 1:
            gaps.append(
                KnowledgeGap(
                    session_id=session_id,
                    gap_type=GapType.MISSING_PREREQUISITE,
                    priority=2,
                    description="Question appears underspecified; prerequisite concepts are missing.",
                )
            )

        if len(concepts) >= 3 and "because" not in text.lower() and "why" in text.lower():
            gaps.append(
                KnowledgeGap(
                    session_id=session_id,
                    gap_type=GapType.WEAK_EVIDENCE,
                    priority=1,
                    description="Claim includes multiple concepts but little explicit evidence linkage.",
                )
            )

        return gaps

    def parse_turn(self, payload: ParseTurnRequest) -> ParseTurnResponse:
        turn = payload.turn
        concepts = self._extract_concepts(turn.content, turn.turn_id)
        relations = self._extract_relations(turn.content, concepts, turn.turn_id)
        coreferences = self._resolve_coreference(payload.tenant_id, payload.session_id, turn.content)
        gaps = self._build_gaps(payload.session_id, turn.content, concepts, coreferences)

        concept_names = [c.canonical_name for c in concepts]
        if concept_names:
            memory_key = self._memory_key(payload.tenant_id, payload.session_id)
            self.session_concept_memory[memory_key].extend(concept_names)
            self.session_concept_memory[memory_key] = self.session_concept_memory[memory_key][-50:]

        return ParseTurnResponse(
            tenant_id=payload.tenant_id,
            session_id=payload.session_id,
            turn_id=turn.turn_id,
            concepts=concepts,
            relations=relations,
            coreferences=coreferences,
            knowledge_gaps=gaps,
        )


class TransformerInferenceParserBackend(ParserBackend):
    def __init__(self, inference_url: str, timeout_seconds: float, fallback: ParserBackend | None = None) -> None:
        self.inference_url = inference_url
        self.timeout_seconds = timeout_seconds
        self.fallback = fallback or HeuristicParserBackend()

    def parse_turn(self, payload: ParseTurnRequest) -> ParseTurnResponse:
        try:
            extracted = self._call_model(payload)
            return self._map_model_output(payload, extracted)
        except Exception:
            return self.fallback.parse_turn(payload)

    def _call_model(self, payload: ParseTurnRequest) -> dict[str, Any]:
        request_body = TransformerParseRequest(
            tenant_id=payload.tenant_id,
            session_id=payload.session_id,
            turn=payload.turn,
            history=payload.history,
        ).model_dump(mode="json")
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.inference_url, json=request_body)
        response.raise_for_status()
        parsed = TransformerParseResponse.model_validate(response.json())
        return parsed.model_dump(mode="json")

    def _map_model_output(self, payload: ParseTurnRequest, extracted: dict[str, Any]) -> ParseTurnResponse:
        turn_id = payload.turn.turn_id
        concept_objects: list[Concept] = []
        concept_id_by_name: dict[str, str] = {}

        for item in extracted.get("concepts", []):
            if not isinstance(item, dict):
                continue
            canonical_name = str(item.get("canonical_name", "")).strip()
            if not canonical_name:
                continue
            concept = Concept(
                canonical_name=canonical_name,
                aliases=[str(v) for v in item.get("aliases", []) if str(v).strip()],
                domain=str(item.get("domain", "general")),
                confidence=float(item.get("confidence", 0.8)),
                evidence_turn_ids=[turn_id],
            )
            concept_objects.append(concept)
            concept_id_by_name[canonical_name.lower()] = concept.node_id

        relation_objects: list[Relation] = []
        for item in extracted.get("relations", []):
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source", "")).strip().lower()
            target_name = str(item.get("target", "")).strip().lower()
            source_node_id = concept_id_by_name.get(source_name)
            target_node_id = concept_id_by_name.get(target_name)
            if not source_node_id or not target_node_id:
                continue

            relation_type_name = str(item.get("relation_type", RelationType.DEFINITION.value))
            try:
                relation_type = RelationType(relation_type_name)
            except ValueError:
                relation_type = RelationType.DEFINITION

            relation_objects.append(
                Relation(
                    source_node_id=source_node_id,
                    target_node_id=target_node_id,
                    relation_type=relation_type,
                    confidence=float(item.get("confidence", 0.75)),
                    evidence_turn_ids=[turn_id],
                )
            )

        coreferences: list[Coreference] = []
        for item in extracted.get("coreferences", []):
            if not isinstance(item, dict):
                continue
            mention = str(item.get("mention", "")).strip()
            resolved_to = str(item.get("resolved_to", "")).strip()
            if not mention or not resolved_to:
                continue
            coreferences.append(
                Coreference(
                    mention=mention,
                    resolved_to=resolved_to,
                    confidence=float(item.get("confidence", 0.75)),
                )
            )

        gaps: list[KnowledgeGap] = []
        for item in extracted.get("knowledge_gaps", []):
            if not isinstance(item, dict):
                continue
            try:
                gap_type = GapType(str(item.get("gap_type")))
            except ValueError:
                continue
            gaps.append(
                KnowledgeGap(
                    session_id=payload.session_id,
                    gap_type=gap_type,
                    priority=int(item.get("priority", 2)),
                    description=str(item.get("description", "Model-signaled knowledge gap.")),
                )
            )

        # Fallback safety for under-specified model output.
        if not concept_objects:
            return self.fallback.parse_turn(payload)

        return ParseTurnResponse(
            tenant_id=payload.tenant_id,
            session_id=payload.session_id,
            turn_id=turn_id,
            concepts=concept_objects,
            relations=relation_objects,
            coreferences=coreferences,
            knowledge_gaps=gaps,
        )


def build_parser_backend() -> ParserBackend:
    backend_name = settings.parser_backend.lower()
    heuristic = HeuristicParserBackend()
    if backend_name == "transformer" and settings.transformer_inference_url:
        return TransformerInferenceParserBackend(
            inference_url=settings.transformer_inference_url,
            timeout_seconds=settings.transformer_timeout_seconds,
            fallback=heuristic,
        )
    return heuristic
