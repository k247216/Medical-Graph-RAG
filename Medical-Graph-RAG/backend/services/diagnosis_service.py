from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from .chain_builder import build_chain
from .context_builder import build_context
from .graph_service import GraphService
from .llm_service import LlmService


class DiagnosisService:
    def __init__(self, graph_service: GraphService, llm_service: LlmService) -> None:
        self._graph_service = graph_service
        self._llm_service = llm_service

    async def get_suggestions(
        self,
        patient_info: str,
        keywords: str,
        top_k: int,
        layers: list[str] | None = None,
        reference_hops: int = 1,
    ) -> dict[str, Any]:
        keyword_list = _parse_keywords(keywords)
        subgraph = await self._graph_service.search_subgraph(
            keyword_list,
            hop=2,
            limit=top_k,
            layers=layers,
            reference_hops=reference_hops,
        )

        context = build_context(subgraph)
        suggestions = await self._llm_service.generate_suggestions(
            patient_info=patient_info,
            keywords=keywords,
            context=context,
        )
        chain = build_chain(subgraph, keyword_list, suggestions)

        return {
            "diagnosis_suggestions": suggestions,
            "diagnosis_chain": chain,
            "graph_summary": subgraph.get("summary", []),
            "layer_stats": subgraph.get("layerStats", {}),
        }

    async def get_suggestions_stream(
        self,
        patient_info: str,
        keywords: str,
        top_k: int,
        layers: list[str] | None = None,
        reference_hops: int = 1,
    ) -> AsyncIterator[str]:
        keyword_list = _parse_keywords(keywords)
        subgraph = await self._graph_service.search_subgraph(
            keyword_list,
            hop=2,
            limit=top_k,
            layers=layers,
            reference_hops=reference_hops,
        )

        # 1. 先发子图数据
        yield json.dumps({
            "type": "graph",
            "data": {
                "nodes": subgraph.get("nodes", []),
                "links": subgraph.get("links", []),
                "summary": subgraph.get("summary", []),
                "layerStats": subgraph.get("layerStats", {}),
            },
        }, ensure_ascii=False)

        await asyncio.sleep(0)  # flush

        # 2. 流式发诊断建议
        context = build_context(subgraph)
        async for delta in self._llm_service.generate_suggestions_stream(
            patient_info=patient_info,
            keywords=keywords,
            context=context,
        ):
            if delta:
                yield json.dumps({
                    "type": "suggestion_chunk",
                    "data": {"delta": delta},
                }, ensure_ascii=False)

        # 3. 诊断链
        keyword_list = _parse_keywords(keywords)
        chain = build_chain(subgraph, keyword_list, [])
        yield json.dumps({
            "type": "chain",
            "data": chain,
        }, ensure_ascii=False)

        # 4. 结束
        yield json.dumps({"type": "done"})


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
