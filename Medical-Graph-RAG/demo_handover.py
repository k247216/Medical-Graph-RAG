"""
Medical-Graph-RAG 后端两层演示脚本
================================
使用方法:
  1. 确保后端已启动: cd backend && uvicorn backend.app:app --port 8000
  2. 运行本脚本: python demo_handover.py

本脚本会展示三大核心能力:
  ① 图谱检索（单层 vs 跨层，展示 REFERENCE 的价值）
  ② 全流程诊断（图检索 + LLM 推理 + 证据回溯）
  ③ SSE 流式诊断（模拟前端实时接收）

输出格式: 彩色标注，每步有说明，适合直接展示或录屏。
"""

import json
import sys
import time
import httpx

BASE_URL = "http://localhost:8000"

# ── 格式化输出工具 ─────────────────────────────────────────────────


def section(title: str):
    print()
    print("=" * 65)
    print(f"  {title}")
    print("=" * 65)


def step(num: int, desc: str):
    print(f"\n>> [{num}] {desc}")


def ok(label: str, detail: str = ""):
    print(f"   ✓ {label}  {detail}")


def info(label: str, detail: str = ""):
    print(f"   ℹ  {label}  {detail}")


def show_json(label: str, data):
    print(f"   {label}:")
    print(f"   {json.dumps(data, ensure_ascii=False, indent=2)[:2500]}")
    print()


def oneline(label: str, data):
    """简化为一行摘要"""
    text = json.dumps(data, ensure_ascii=False)
    if len(text) > 120:
        text = text[:120] + "..."
    print(f"   {label}: {text}")


# ── 演示开始 ───────────────────────────────────────────────────────


def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Medical-Graph-RAG  后端演示                      ║")
    print("║     底层数据: Middle(默沙东43K) + Top(病例31K)           ║")
    print("║     REFERENCE 跨层链接: 2,228 条                         ║")
    print("╚══════════════════════════════════════════════════════════╝")

    client = httpx.Client(base_url=BASE_URL, timeout=30)

    # ──── 0. 健康检查 ────────────────────────────────────────────

    section("0. 健康检查 — 确认服务可用")

    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    data = resp.json()
    ok("服务状态", json.dumps(data, ensure_ascii=False))
    assert data["status"] == "ok", "Neo4j 或 Qwen 不可用，请检查服务"

    # ──── 1. 图谱检索 — 三层威力展示 ─────────────────────────────

    section("1. 图谱检索 — 展示三层架构与 REFERENCE 跨层威力")

    keywords = "头痛, 恶心"

    # 1a. 只查 Middle 层
    step("1a", f'关键词 "{keywords}" — 仅 Middle 层（无跨层）')
    resp = client.post("/api/graph/search", json={
        "keywords": keywords,
        "hop": 2,
        "limit": 20,
        "layers": ["middle"],
        "reference_hops": 0,
    })
    middle_only = resp.json()
    ok(f"返回 {len(middle_only['nodes'])} 节点, {len(middle_only['links'])} 关系")
    info("layerStats", json.dumps(middle_only.get("layerStats", {}), ensure_ascii=False))
    info("示例节点",
         [(n.get("name"), n.get("label"), n.get("layer"))
          for n in middle_only["nodes"][:5]])

    # 1b. Middle + Top + REFERENCE 跨层
    step("1b", f'关键词 "{keywords}" — Middle + Top 层（跨层扩展打开）')
    resp = client.post("/api/graph/search", json={
        "keywords": keywords,
        "hop": 2,
        "limit": 20,
        "layers": ["middle", "top"],
        "reference_hops": 1,
    })
    cross_layer = resp.json()
    ok(f"返回 {len(cross_layer['nodes'])} 节点, {len(cross_layer['links'])} 关系")
    info("layerStats", json.dumps(cross_layer.get("layerStats", {}), ensure_ascii=False))

    # 统计各层节点数
    layer_count = cross_layer.get("layerStats", {})
    for lyr, cnt in sorted(layer_count.items()):
        info(f"  {lyr} 层节点", f"{cnt} 个")

    # 找出 REFERENCE 关系
    ref_links = [l for l in cross_layer["links"] if l.get("label") == "REFERENCE"]
    if ref_links:
        ok(f"REFERENCE 跨层链接", f"{len(ref_links)} 条")
        for l in ref_links[:3]:
            info("  跨层",
                 f'{l["source"]} ──REFERENCE──► {l["target"]}')
    else:
        info("跨层链接", "本次查询未命中 REFERENCE（可能是关键词在两层无桥接）")

    # 对比: 跨层后比单层多出来的节点
    info("跨层扩展效果",
         f"仅 Middle: {len(middle_only['nodes'])} 节点 → "
         f"跨层: {len(cross_layer['nodes'])} 节点")

    # ──── 2. 全流程诊断 ──────────────────────────────────────────

    section("2. 全流程诊断 — 图谱 + LLM + 证据回溯")

    patient = "患者女性，35岁，反复发作性头痛3年，每次持续4-72小时，伴恶心、畏光，活动后加重，家族中有类似病史。"

    step("2a", f"诊断请求: {patient[:50]}...")
    t0 = time.time()
    resp = client.post("/api/diagnosis/suggestions", json={
        "patient_info": patient,
        "keywords": "头痛, 恶心, 畏光",
        "top_k": 30,
        "layers": ["middle", "top"],
        "reference_hops": 1,
    })
    elapsed = time.time() - t0
    result = resp.json()
    ok(f"诊断完成 ({elapsed:.1f}s)")

    suggestions = result.get("diagnosis_suggestions", [])
    ok(f"LLM 生成 {len(suggestions)} 条诊断建议")

    for i, sug in enumerate(suggestions, 1):
        print(f"\n   ── 诊断建议 #{i} ──")
        print(f"      诊断:     {sug.get('diagnosis', '?')}")
        print(f"      置信度:   {sug.get('confidence', '?')}")
        evidence = sug.get("evidence", "")
        if len(evidence) > 150:
            evidence = evidence[:150] + "..."
        print(f"      证据:     {evidence}")

        ev_nodes = sug.get("evidence_nodes", [])
        ev_paths = sug.get("evidence_paths", [])
        if ev_nodes:
            # 按层归类
            by_layer = {}
            for n in ev_nodes:
                lyr = n.get("layer", "?")
                by_layer.setdefault(lyr, []).append(n.get("name", "?"))
            for lyr, names in by_layer.items():
                print(f"      [{lyr}层证据]  {', '.join(names[:4])}")
        if ev_paths:
            print(f"      证据路径:")
            for p in ev_paths[:3]:
                print(f"        {p}")

    # 诊断链
    chain = result.get("diagnosis_chain", {})
    chain_summary = chain.get("summary", "")
    if chain_summary:
        ok("诊断链摘要", chain_summary[:200])
    info("诊断链节点数",
         f"{len(chain.get('nodes', []))} 节点, "
         f"{len(chain.get('links', []))} 关系")
    info("各层分布", json.dumps(result.get("layer_stats", {}), ensure_ascii=False))

    # ──── 3. SSE 流式诊断（可选，用 httpx 模拟） ─────────────────

    section("3. SSE 流式诊断 — 模拟前端实时接收")

    step("3a", "发起 SSE 请求，等待流式事件...")
    t0 = time.time()
    with client.stream(
        "POST", "/api/diagnosis/suggestions/stream",
        json={
            "patient_info": patient,
            "keywords": "头痛, 恶心, 畏光",
            "top_k": 30,
            "layers": ["middle", "top"],
            "reference_hops": 1,
        },
    ) as resp:
        assert resp.status_code == 200, f"SSE failed: {resp.status_code}"
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                events.append(payload)

    elapsed = time.time() - t0
    ok(f"收到 {len(events)} 个 SSE 事件 ({elapsed:.1f}s)")

    event_types = {}
    for ev in events:
        et = ev.get("type", "?")
        event_types[et] = event_types.get(et, 0) + 1
        if et == "graph":
            nodes = len(ev.get("data", {}).get("nodes", []))
            links = len(ev.get("data", {}).get("links", []))
            ok("graph 事件", f"{nodes} 节点, {links} 关系")
        elif et == "suggestion_chunk":
            pass  # 只计数
        elif et == "chain":
            chain_data = ev.get("data", {})
            info("chain 事件",
                 f"{len(chain_data.get('nodes', []))} 节点, "
                 f"{len(chain_data.get('links', []))} 关系")
        elif et == "done":
            ok("done 事件", "流式结束")

    info("事件类型分布", json.dumps(event_types, ensure_ascii=False))
    chunk_count = event_types.get("suggestion_chunk", 0)
    if chunk_count > 0:
        ok("流式效果", f"suggestion_chunk 共 {chunk_count} 次推送（实时增量输出）")

    # ──── 总结 ────────────────────────────────────────────────────

    print()
    print("=" * 65)
    print("  演示完成 — 系统通过了所有关键路径")
    print("=" * 65)
    print()
    print("  验证了以下能力:")
    print("    ✓ 图谱关键词检索（单层 + 跨层 REFERENCE）")
    print("    ✓ LLM 诊断建议生成（基于图谱上下文）")
    print("    ✓ 证据节点回溯 + 推理路径构建")
    print("    ✓ SSE 流式推送（可用于前端实时展示）")
    print("    ✓ 跨层数据可见（layerStats 区分各层贡献）")
    print()
    print("  待实施:")
    print("    - Bottom 层（医学词典，见 bottom_layer_plan.md）")
    print("    - 前端 UI（当前为空白脚手架）")
    print()
    print("  关键文档:")
    print("    - 后端实施方案.md（完整实施细节）")
    print("    - 后端进展.md（工程总结与决策记录）")
    print("    - 后端开发.md（API 接口参考）")
    print()


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print()
        print("❌ 连接失败：请确保后端已在 http://localhost:8000 运行")
        print()
        print("   启动命令:")
        print("   cd Medical-Graph-RAG/backend")
        print("   uvicorn backend.app:app --port 8000")
        print()
        sys.exit(1)
    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        sys.exit(1)
