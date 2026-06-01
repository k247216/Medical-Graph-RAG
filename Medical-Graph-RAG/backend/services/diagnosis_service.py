from __future__ import annotations

from typing import Any

from .chain_builder import build_chain
from .context_builder import build_context
from .graph_service import GraphService
from .llm_service import LlmService


class DiagnosisService:
    def __init__(self, graph_service: GraphService, llm_service: LlmService) -> None:
        self._graph_service = graph_service
        self._llm_service = llm_service

    def get_suggestions(
        self,
        patient_info: str,
        keywords: str,
        top_k: int,
    ) -> dict[str, Any]:
        keyword_list = _parse_keywords(keywords)
        subgraph = self._graph_service.search_subgraph(
            keyword_list,
            hop=2,
            limit=top_k,
        )
        context = build_context(subgraph)
        suggestions = self._llm_service.generate_suggestions(
            patient_info=patient_info,
            keywords=keywords,
            context=context,
        )
        chain = build_chain(subgraph, keyword_list, suggestions)
        return {
            "diagnosis_suggestions": suggestions,
            "diagnosis_chain": chain,
        }


def _parse_keywords(value: str) -> list[str]:
    if not value:
        return []
    tokens = [token.strip() for token in value.replace(";", ",").split(",")]
    keywords = []
    for token in tokens:
        if not token:
            continue
        for part in token.split():
            if part:
                keywords.append(part)
    return keywords
