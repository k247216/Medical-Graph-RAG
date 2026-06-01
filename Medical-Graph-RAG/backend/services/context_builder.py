from __future__ import annotations

from typing import Any


def build_context(subgraph: dict[str, Any], max_nodes: int = 30, max_links: int = 60) -> str:
    nodes = subgraph.get("nodes", [])[:max_nodes]
    links = subgraph.get("links", [])[:max_links]

    lines: list[str] = []
    for node in nodes:
        label = node.get("label", "")
        name = node.get("name", "")
        lines.append(f"Node: {label} | {name}")

    for link in links:
        source = link.get("source", "")
        target = link.get("target", "")
        rel = link.get("label", "")
        lines.append(f"Rel: {source} -[{rel}]-> {target}")

    return "\n".join(lines)
