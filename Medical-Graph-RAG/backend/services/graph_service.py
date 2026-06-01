from __future__ import annotations

from typing import Any

from camel.storages import Neo4jGraph

from ..config import Settings


class GraphService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
        )

    def health_check(self) -> bool:
        try:
            result = self._graph.query("RETURN 1 AS ok")
            return bool(result and result[0].get("ok") == 1)
        except Exception:
            return False

    def search_subgraph(self, keywords: list[str], hop: int, limit: int) -> dict[str, Any]:
        if not keywords:
            return {"nodes": [], "links": []}

        cypher = """
        MATCH (n)
        WHERE any(k IN $keywords WHERE toLower(coalesce(n.name, n.id, "")) CONTAINS k)
        WITH collect(distinct n) AS seeds
        UNWIND seeds AS s
        OPTIONAL MATCH (s)-[*1..$hop]-(m)
        WITH collect(distinct s) + collect(distinct m) AS all_nodes
        UNWIND all_nodes AS n
        WITH distinct n LIMIT $limit
        WITH collect(n) AS nodes
        UNWIND nodes AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN nodes
        RETURN
            collect(distinct {
                id: coalesce(n.id, n.name, toString(id(n))),
                label: head(labels(n)),
                name: coalesce(n.name, n.id, ""),
                properties: properties(n)
            }) AS nodes,
            collect(distinct CASE WHEN r IS NULL THEN null ELSE {
                source: coalesce(n.id, n.name, toString(id(n))),
                target: coalesce(m.id, m.name, toString(id(m))),
                label: type(r),
                properties: properties(r)
            } END) AS links
        """

        result = self._graph.query(
            cypher,
            {
                "keywords": [k.lower() for k in keywords],
                "hop": hop,
                "limit": limit,
            },
        )
        if not result:
            return {"nodes": [], "links": []}

        nodes = result[0].get("nodes", []) or []
        links = [link for link in (result[0].get("links", []) or []) if link]
        return {"nodes": nodes, "links": links}
