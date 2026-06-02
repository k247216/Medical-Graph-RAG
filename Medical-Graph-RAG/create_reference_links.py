"""
创建跨层 REFERENCE 链接 — 稀疏版本
每个 Middle 子图只连 Top-K 个最相似的 Top 节点（默认 K=10）
"""
import os
import sys
import numpy as np
from collections import defaultdict

from n4j_shim import Neo4jGraph

THRESHOLD = 0.55
TOP_K = 10


def cosine_similarity_batch(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """计算 query 与所有 candidates 的余弦相似度"""
    query_norm = query / (np.linalg.norm(query) + 1e-8)
    candidates_norm = candidates / (np.linalg.norm(candidates, axis=1, keepdims=True) + 1e-8)
    return np.dot(candidates_norm, query_norm)


def main():
    neo4j_url = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_pass = os.getenv('NEO4J_PASSWORD')

    if not neo4j_pass:
        print("❌ 未设置 NEO4J_PASSWORD")
        sys.exit(1)

    n4j = Neo4jGraph(url=neo4j_url, username=neo4j_user, password=neo4j_pass)

    # 1. 获取 Middle 层 Summary 节点（每个 gid 一个）
    print("[加载] Middle Summary 节点...")
    mid_summaries = n4j.query("""
        MATCH (s:Summary)
        WHERE EXISTS { MATCH (s)-[:SUMMARIZES]->(n) WHERE n.layer = 'middle' }
        RETURN s.content AS text, s.gid AS gid
    """)
    print(f"  Middle Summary: {len(mid_summaries)}")

    # 获取 Middle gid 的平均 embedding
    mid_gid_embs = {}
    mid_records = n4j.query("""
        MATCH (n) WHERE n.layer = 'middle' AND NOT n:Summary AND n.embedding IS NOT NULL
        RETURN n.gid AS gid, n.embedding AS embedding
    """)

    gid_embs = defaultdict(list)
    for r in mid_records:
        if r['embedding']:
            gid_embs[r['gid']].append(r['embedding'])

    for gid, embs in gid_embs.items():
        mid_gid_embs[gid] = np.mean(embs, axis=0)

    middle_gids = list(mid_gid_embs.keys())
    print(f"  Middle gid with embeddings: {len(middle_gids)}")

    # 2. 获取 Top 层节点及 embedding
    print("[加载] Top 层节点...")
    top_records = n4j.query("""
        MATCH (n) WHERE n.layer = 'top' AND NOT n:Summary AND n.embedding IS NOT NULL
        RETURN n.id AS id, n.embedding AS embedding, labels(n)[0] AS label
    """)
    print(f"  Top 节点: {len(top_records)}")

    top_ids = [r['id'] for r in top_records]
    top_embs = np.array([r['embedding'] for r in top_records], dtype=np.float32)
    print(f"  Top embedding matrix: {top_embs.shape}")

    # 3. 对每个 Middle gid，找 top-K 最相似的 Top 节点
    print(f"\n[匹配] 每个 Middle gid → Top-{TOP_K} (threshold={THRESHOLD})...")
    total_links = 0

    for i, gid in enumerate(middle_gids):
        mid_emb = mid_gid_embs[gid]
        sims = cosine_similarity_batch(mid_emb, top_embs)

        # 找 top-K
        top_indices = np.argsort(sims)[-TOP_K:][::-1]  # descending

        count = 0
        for idx in top_indices:
            sim = float(sims[idx])
            if sim < THRESHOLD:
                continue

            top_id = top_ids[idx]
            try:
                # 创建 REFERENCE: Middle Summary ← Top node
                n4j.query("""
                    MATCH (s:Summary) WHERE s.gid = $gid
                    MATCH (t) WHERE t.id = $top_id AND t.layer = 'top'
                    MERGE (t)-[:REFERENCE]->(s)
                """, {'gid': gid, 'top_id': top_id})
                count += 1
            except Exception as e:
                pass

        total_links += count
        if (i + 1) % 200 == 0 or count > 0:
            print(f"  [{i+1}/{len(middle_gids)}] {gid[:8]}... → {count} refs (top sim={float(sims[top_indices[0]]):.3f})")

    print(f"\n{'='*60}")
    print(f"完成: 共创建 {total_links} 条 REFERENCE 链接")

    # 验证
    count = n4j.query("MATCH ()-[r:REFERENCE]->() RETURN count(r) as count")
    print(f"验证: 数据库中共 {count[0]['count']} 条 REFERENCE 关系")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
