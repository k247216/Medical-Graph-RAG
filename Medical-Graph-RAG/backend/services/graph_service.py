from __future__ import annotations

import asyncio
import json
from typing import Any

from neo4j import GraphDatabase

from ..config import Settings


class GraphService:
    def __init__(self, settings: Settings) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            max_connection_lifetime=300,
            max_connection_pool_size=20,
            connection_acquisition_timeout=10,
        )

    async def health_check(self) -> bool:
        try:
            result = await asyncio.to_thread(
                lambda: self._driver.execute_query("RETURN 1 AS ok")
            )
            return bool(result.records and result.records[0].get("ok") == 1)
        except Exception:
            return False

    async def search_subgraph(
        self,
        keywords: list[str],
        hop: int,
        limit: int,
        layers: list[str] | None = None,
        reference_hops: int = 0,
    ) -> dict[str, Any]:
        if layers is None:
            layers = ["bottom", "middle", "top"]

        if not keywords:
            return {"nodes": [], "links": [], "summary": [], "layerStats": {}}

        keyword_values = [k.lower() for k in keywords]
        max_total = min(limit * 2, 200)

        # hop/reference_hops 已经由 Pydantic 校验范围，安全拼接
        cypher = f"""
        // 第一步：按关键词 + layer 过滤种子节点
        MATCH (n)
        WHERE any(k IN $keywords WHERE toLower(coalesce(n.id, n.name, "")) CONTAINS k)
          AND n.layer IN $layers
          AND NOT n:Summary AND NOT n:Chunk
        WITH collect(DISTINCT n) AS seeds

        // 第二步：沿普通关系扩展 {hop} 跳
        UNWIND seeds AS s
        OPTIONAL MATCH (s)-[*1..{hop}]-(m)
        WHERE NOT m:Summary AND NOT m:Chunk AND m.layer IN $layers
        WITH seeds, collect(DISTINCT m) AS neighbors
        WITH seeds + neighbors AS expanded
        UNWIND expanded AS n
        WITH DISTINCT n LIMIT {max_total}
        WITH collect(n) AS base_nodes

        // 第三步：通过 Summary 桥接 + REFERENCE 跨层扩展
        // 路径: base_node ← SUMMARIZES ← Summary ← REFERENCE → cross_layer_node
        OPTIONAL MATCH (bn)-[:SUMMARIZES]-(s:Summary)-[:REFERENCE]-(ref)
        WHERE bn IN base_nodes
          AND NOT ref:Summary AND NOT ref:Chunk
          AND ref.layer IN $layers
        WITH base_nodes, collect(DISTINCT ref) AS ref_nodes
        WITH base_nodes + ref_nodes AS all_nodes
        UNWIND all_nodes AS n
        WITH DISTINCT n
        WITH collect(n) AS graph_nodes

        // 第四步：收集节点内关系
        UNWIND graph_nodes AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN graph_nodes AND NOT m:Summary AND NOT m:Chunk
        RETURN
            collect(DISTINCT {{
                id: coalesce(n.id, n.name, toString(id(n))),
                label: head(labels(n)),
                name: coalesce(n.name, n.id, ""),
                layer: n.layer,
                gid: n.gid,
                properties: properties(n)
            }}) AS nodes,
            collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE {{
                source: coalesce(startNode(r).id, startNode(r).name, toString(id(startNode(r)))),
                target: coalesce(endNode(r).id, endNode(r).name, toString(id(endNode(r)))),
                label: type(r),
                properties: properties(r)
            }} END) AS links
        """

        try:
            result = await asyncio.to_thread(
                lambda: self._driver.execute_query(
                    cypher,
                    keywords=keyword_values,
                    layers=layers,
                )
            )
        except Exception:
            return {"nodes": [], "links": [], "summary": [], "layerStats": {}}

        record = result.records[0] if result.records else None
        if not record:
            return {"nodes": [], "links": [], "summary": [], "layerStats": {}}

        raw_nodes = record.get("nodes") or []
        raw_links = [link for link in (record.get("links") or []) if link]

        # 过滤 embedding 向量和不可序列化的类型
        for node in raw_nodes:
            props = node.get("properties") or {}
            props.pop("embedding", None)
            # 转换 Neo4j 特殊类型为 string
            clean_props = {}
            for k, v in props.items():
                try:
                    json.dumps({k: v})
                    clean_props[k] = v
                except (TypeError, ValueError):
                    clean_props[k] = str(v)
            node["properties"] = clean_props

        # 去重并限制数量，确保跨层节点不被全部截断
        layer_nodes: dict[str, list] = {}
        seen_ids = set()
        for n in raw_nodes:
            nid = n.get("id", "")
            if nid not in seen_ids:
                seen_ids.add(nid)
                layer = n.get("layer", "unknown")
                layer_nodes.setdefault(layer, []).append(n)

        # 交错排列各层节点，每层最多 limit/2
        per_layer = max(limit // max(len(layer_nodes), 1), 1)
        nodes = []
        for lyr in layer_nodes:
            nodes.extend(layer_nodes[lyr][:per_layer])
        seen_ids = {n.get("id") for n in nodes}

        # 如果还不够 limit，继续填充
        if len(nodes) < limit:
            for n in raw_nodes:
                nid = n.get("id", "")
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    nodes.append(n)
                    if len(nodes) >= limit:
                        break

        seen_links = set()
        links = []
        for link in raw_links:
            key = (link.get("source"), link.get("target"), link.get("label"))
            if key not in seen_links:
                seen_links.add(key)
                links.append(link)

        # 查询 Summary
        node_ids = [n["id"] for n in nodes]
        summaries = await self._query_summaries(node_ids)

        # 计算 layerStats
        layer_stats = self._compute_layer_stats(nodes)

        return {
            "nodes": nodes,
            "links": links,
            "summary": summaries,
            "layerStats": layer_stats,
        }

    async def _query_summaries(self, node_ids: list[str]) -> list[dict[str, str]]:
        if not node_ids:
            return []

        cypher = """
        MATCH (s:Summary)-[:SUMMARIZES]->(n)
        WHERE n.id IN $ids OR n.name IN $ids
        RETURN DISTINCT toString(s.content) AS text, s.gid AS gid
        LIMIT 10
        """
        try:
            result = await asyncio.to_thread(
                lambda: self._driver.execute_query(cypher, ids=node_ids)
            )
            summaries = []
            for r in result.records:
                text = r.get("text", "")
                if isinstance(text, list):
                    text = "; ".join(str(t) for t in text)
                summaries.append({"text": str(text), "gid": str(r.get("gid", ""))})
            return summaries
        except Exception:
            return []

    @staticmethod
    def _compute_layer_stats(nodes: list[dict[str, Any]]) -> dict[str, int]:
        stats: dict[str, int] = {}
        for node in nodes:
            layer = node.get("layer", "unknown")
            stats[layer] = stats.get(layer, 0) + 1
        return stats
