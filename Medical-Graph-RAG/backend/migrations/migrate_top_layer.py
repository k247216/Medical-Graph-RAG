"""
迁移现有 Neo4j 数据为三层架构的 Top 层。
补写: id(缺则从 name 复制), gid, embedding, layer, description
"""

import os
import sys
from uuid import uuid4

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
if not NEO4J_PASSWORD:
    print("请设置环境变量 NEO4J_PASSWORD")
    sys.exit(1)

TOP_GID = str(uuid4())
BATCH = 200


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    print(f"[连接] Neo4j: {NEO4J_URI}")

    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    print(f"[Embedding] BGE-small-zh 已加载 (dim={model.get_sentence_embedding_dimension()})")

    with driver.session() as session:
        # 1. 补写 id 属性
        result = session.run("""
            MATCH (n) WHERE n.id IS NULL AND n.name IS NOT NULL AND NOT n:Summary AND NOT n:Chunk
            SET n.id = n.name
            RETURN count(n) AS cnt
        """)
        print(f"[ID补写] {result.single()['cnt']} 个节点")

        # 2. 补写 description（合并可用文本字段）
        result = session.run("""
            MATCH (n) WHERE n.description IS NULL AND NOT n:Summary AND NOT n:Chunk
            SET n.description = coalesce(
                n.summary, n.summary_en, n.name_en + ': ' + n.name,
                n.name_zh, n.name,
                n.norm, ''
            )
            RETURN count(n) AS cnt
        """)
        print(f"[Description] {result.single()['cnt']} 个节点")

        # 3. 设置 layer 和 gid
        result = session.run("""
            MATCH (n) WHERE NOT n:Summary AND NOT n:Chunk
            SET n.layer = 'top', n.gid = $gid
            RETURN count(n) AS cnt
        """, gid=TOP_GID)
        top_count = result.single()["cnt"]
        print(f"[Layer/GID] {top_count} 个节点 -> layer='top', gid={TOP_GID[:8]}...")

        # 4. 分批生成 embedding
        nodes_result = session.run("""
            MATCH (n) WHERE NOT n:Summary AND NOT n:Chunk AND n.embedding IS NULL
            RETURN id(n) AS neo4j_id, n.id AS node_id, n.description AS desc
        """)
        nodes = list(nodes_result)
        print(f"[Embedding] 待处理: {len(nodes)} 个节点")

        for i in range(0, len(nodes), BATCH):
            batch = nodes[i:i + BATCH]
            texts = [
                f"{n['node_id']}: {n.get('desc', '')}" if n.get('desc') else (n['node_id'] or "")
                for n in batch
            ]
            embeddings = model.encode(texts).tolist()

            for j, node in enumerate(batch):
                session.run(
                    "MATCH (n) WHERE id(n) = $neo4j_id SET n.embedding = $emb",
                    neo4j_id=node["neo4j_id"], emb=embeddings[j],
                )
            print(f"  [{i + len(batch)}/{len(nodes)}] 完成")

        # 5. 汇总
        result = session.run("""
            MATCH (n) WHERE n.layer = 'top' AND n.embedding IS NOT NULL
            RETURN count(n) AS cnt
        """)
        print(f"\n✅ Top 层迁移完成: {result.single()['cnt']} 个节点")
        print(f"   gid: {TOP_GID}")
        print(f"   layer: top")

    driver.close()


if __name__ == "__main__":
    main()
