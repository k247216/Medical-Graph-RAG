from __future__ import annotations

from typing import Any


def build_context(
    subgraph: dict[str, Any],
    max_nodes: int = 30,
    max_links: int = 60,
) -> str:
    nodes = subgraph.get("nodes", [])[:max_nodes]
    links = subgraph.get("links", [])[:max_links]
    summaries = subgraph.get("summary", [])

    lines: list[str] = []

    # Summary 优先展示
    if summaries:
        lines.append("=== Subgraph Summaries ===")
        for s in summaries[:5]:
            gid_short = str(s.get("gid", ""))[:8]
            text = str(s.get("text", ""))[:300]
            lines.append(f"Summary (gid={gid_short}): {text}")
        lines.append("")

    # 节点（含层级标注）
    lines.append("=== Relevant Entities ===")
    for node in nodes:
        label = node.get("label", "")
        name = node.get("name", "")
        layer = node.get("layer", "")
        desc = node.get("properties", {}).get("description", "")
        layer_tag = f"[{layer}]" if layer else ""
        desc_tag = f" - {desc[:80]}" if desc else ""
        lines.append(f"Node{layer_tag}: {label} | {name}{desc_tag}")

    # 关系
    lines.append("=== Relationships ===")
    for link in links:
        source = link.get("source", "")
        target = link.get("target", "")
        rel = link.get("label", "")
        lines.append(f"Rel: {source} -[{rel}]-> {target}")

    return "\n".join(lines)
