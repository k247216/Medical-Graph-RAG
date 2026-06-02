from __future__ import annotations

from typing import Any


def build_chain(
    subgraph: dict[str, Any],
    keywords: list[str],
    suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = subgraph.get("nodes", [])
    links: list[dict[str, Any]] = subgraph.get("links", [])

    keyword_set = {k.lower() for k in keywords}
    diagnosis_names = {
        str(item.get("diagnosis", "")).lower() for item in suggestions if item
    }

    def node_key(node: dict[str, Any]) -> str:
        return str(node.get("id", ""))

    def matches(node: dict[str, Any]) -> bool:
        name = str(node.get("name", "")).lower()
        return any(key and key in name for key in keyword_set) or \
            any(key and key in name for key in diagnosis_names)

    # 1. 种子节点
    selected_nodes = [n for n in nodes if matches(n)]
    selected_ids = {node_key(n) for n in selected_nodes}

    # 2. 沿 REFERENCE 跨层扩展
    ref_links = [l for l in links if l.get("label") == "REFERENCE"]
    for link in ref_links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in selected_ids:
            target = next((n for n in nodes if node_key(n) == tgt), None)
            if target and target not in selected_nodes:
                selected_nodes.append(target)
                selected_ids.add(tgt)
        if tgt in selected_ids:
            source = next((n for n in nodes if node_key(n) == src), None)
            if source and source not in selected_nodes:
                selected_nodes.append(source)
                selected_ids.add(src)

    # 3. 链内关系
    selected_links = [
        l for l in links
        if l.get("source") in selected_ids and l.get("target") in selected_ids
    ]

    # 4. 回退
    if not selected_nodes:
        selected_nodes = nodes[:10]
        selected_ids = {node_key(n) for n in selected_nodes}
        selected_links = [
            l for l in links
            if l.get("source") in selected_ids and l.get("target") in selected_ids
        ]

    summary = _summarize_chain(selected_nodes, selected_links)
    return {"nodes": selected_nodes, "links": selected_links, "summary": summary}


def _summarize_chain(
    nodes: list[dict[str, Any]], links: list[dict[str, Any]]
) -> str:
    if not nodes:
        return "No matching chain found in the subgraph."

    parts: list[str] = []
    for link in links[:5]:
        source = link.get("source", "")
        target = link.get("target", "")
        rel = link.get("label", "")
        parts.append(f"{source} -[{rel}]-> {target}")

    if parts:
        return " | ".join(parts)

    names = [n.get("name", "") for n in nodes[:3]]
    return " -> ".join(n for n in names if n)
