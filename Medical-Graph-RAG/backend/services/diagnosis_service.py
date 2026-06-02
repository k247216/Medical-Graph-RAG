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

        # 为每条诊断建议匹配图谱中的证据节点和路径
        for s in suggestions:
            evidence_nodes, evidence_paths = _match_evidence(
                s, subgraph, keyword_list
            )
            s["evidence_nodes"] = evidence_nodes
            s["evidence_paths"] = evidence_paths

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


def _match_evidence(
    suggestion: dict[str, Any],
    subgraph: dict[str, Any],
    keywords: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """将诊断建议匹配回图谱，提取该诊断专属的证据节点和证据路径。"""
    nodes: list[dict[str, Any]] = subgraph.get("nodes", [])
    links: list[dict[str, Any]] = subgraph.get("links", [])

    if not nodes:
        return [], []

    diagnosis = str(suggestion.get("diagnosis", ""))
    evidence_text = str(suggestion.get("evidence", ""))
    keyword_set = {k.lower() for k in keywords}

    node_by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        nid = str(n.get("id", ""))
        if nid:
            node_by_id[nid] = n

    # 从证据文本和诊断名中提取关键词
    evidence_lower = evidence_text.lower()
    diag_lower = diagnosis.lower()

    def _in_evidence_or_diag(text: str) -> bool:
        t = text.lower()
        return t in evidence_lower or t in diag_lower

    # 构建词集合：诊断名拆分 + 证据中出现的图谱节点名
    diag_words = [w for w in diag_lower.split() if len(w) >= 2]
    evidence_kw: set[str] = set(diag_words)
    for node in nodes:
        node_name = str(node.get("name", ""))
        if len(node_name) >= 2 and node_name.lower() in evidence_lower:
            evidence_kw.add(node_name.lower())

    # 排除与患者画像明显矛盾的节点（如儿科、产科术语）
    _pediatric_terms = {"新生儿", "婴儿", "儿童", "幼儿", "小儿", "妊娠", "孕妇", "产褥", "先天性"}
    def _is_irrelevant(name: str) -> bool:
        nl = name.lower()
        return any(t in nl for t in _pediatric_terms)

    def _node_matches(n: dict[str, Any]) -> bool:
        node_name = str(n.get("name", ""))
        node_id = str(n.get("id", ""))
        desc = str(n.get("properties", {}).get("description", ""))

        if _is_irrelevant(node_name) or _is_irrelevant(node_id):
            return False

        # 诊断名直接命中节点名
        if diag_lower and (
            diag_lower in node_name.lower()
            or node_name.lower() in diag_lower
        ):
            return True

        # 证据文本中提到该节点
        if len(node_name) >= 2 and _in_evidence_or_diag(node_name):
            return True

        # 节点 id/描述 匹配证据关键词
        for kw in evidence_kw:
            if kw in node_name.lower() or kw in node_id.lower() or kw in desc.lower():
                return True

        # 用户关键词命中节点
        for kw in keyword_set:
            if kw and (kw in node_name.lower() or kw in node_id.lower() or kw in desc.lower()):
                return True

        return False

    matched = [n for n in nodes if _node_matches(n)]
    if not matched:
        matched = nodes[:min(len(nodes), 5)]

    matched_ids = {str(n.get("id", "")) for n in matched}

    # 找匹配节点之间的边作为证据路径
    paths: list[str] = []
    seen_path_keys: set[tuple[str, str, str]] = set()
    for link in links:
        src = str(link.get("source", ""))
        tgt = str(link.get("target", ""))
        rel = str(link.get("label", ""))
        if src in matched_ids and tgt in matched_ids:
            pkey = (src, tgt, rel)
            if pkey not in seen_path_keys:
                seen_path_keys.add(pkey)
                src_name = node_by_id.get(src, {}).get("name", src)
                tgt_name = node_by_id.get(tgt, {}).get("name", tgt)
                paths.append(f"{src_name} -[{rel}]-> {tgt_name}")

    # 构建证据节点（优先放诊断直接命中的节点靠前）
    evidence_nodes: list[dict[str, Any]] = []
    for n in matched[:8]:
        node_name = str(n.get("name", ""))
        is_primary = diag_lower and (
            diag_lower in node_name.lower()
            or node_name.lower() in diag_lower
        )
        evidence_nodes.append({
            "id": n.get("id", ""),
            "name": node_name,
            "label": n.get("label", ""),
            "layer": n.get("layer", ""),
        })
        if is_primary and len(evidence_nodes) > 1:
            # 诊断命中的节点移到首位
            evidence_nodes.insert(0, evidence_nodes.pop())

    return evidence_nodes, paths[:10]
