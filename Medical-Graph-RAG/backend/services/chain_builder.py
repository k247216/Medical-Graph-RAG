from __future__ import annotations

from typing import Any


def build_chain(
    subgraph: dict[str, Any],
    keywords: list[str],
    suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = subgraph.get("nodes", [])
    links = subgraph.get("links", [])

    keyword_set = {k.lower() for k in keywords}
    diagnosis_names = {
        str(item.get("diagnosis", "")).lower() for item in suggestions if item
    }

    def node_key(node: dict[str, Any]) -> str:
        return str(node.get("id", ""))

    def matches(node: dict[str, Any]) -> bool:
        name = str(node.get("name", "")).lower()
        if any(key and key in name for key in keyword_set):
            return True
        if any(key and key in name for key in diagnosis_names):
            return True
        return False

    selected_nodes = [node for node in nodes if matches(node)]
    selected_ids = {node_key(node) for node in selected_nodes}

    selected_links = [
        link
        for link in links
        if link.get("source") in selected_ids and link.get("target") in selected_ids
    ]

    if not selected_nodes:
        selected_nodes = nodes[:10]
        selected_ids = {node_key(node) for node in selected_nodes}
        selected_links = [
            link
            for link in links
            if link.get("source") in selected_ids and link.get("target") in selected_ids
        ]

    summary = _summarize_chain(selected_nodes, selected_links)
    return {"nodes": selected_nodes, "links": selected_links, "summary": summary}


def _summarize_chain(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> str:
    if not nodes:
        return "No matching chain found in the subgraph."

    parts: list[str] = []
    for link in links[:3]:
        source = link.get("source", "")
        target = link.get("target", "")
        rel = link.get("label", "")
        parts.append(f"{source} -[{rel}]-> {target}")

    if parts:
        return " | ".join(parts)

    names = [node.get("name", "") for node in nodes[:3]]
    return " -> ".join([name for name in names if name])
