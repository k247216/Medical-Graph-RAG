# Bottom 层实施方案（交接文档）

## 背景

三层架构：Bottom（医学词典/基础知识）↔ Middle（诊疗指南/教科书）↔ Top（病例）

当前状态：
- Middle 层：43,103 节点（默沙东诊疗手册 2,336 篇），2,550 个 Summary
- Top 层：31,267 节点（已迁移病例），2,228 条 REFERENCE 跨层链接
- Bottom 层：未实施

## 推荐方案：CMeKG 导入 + LLM 补全

CMeKG（Chinese Medical Knowledge Graph）是开源中文医学知识图谱，包含 ~100K 实体和数百万条关系，覆盖疾病、症状、药物、诊疗等结构化知识。

### 步骤 1：获取 CMeKG 数据

- 项目地址：https://github.com/king-yyf/CMeKG_tools
- 数据格式：CSV/JSON，包含实体列表和关系三元组
- 重点获取：
  - `disease.csv` — 疾病实体及属性（ICD编码、科室、病因等）
  - `symptom.csv` — 症状实体
  - `drug.csv` — 药物实体及属性（剂量、禁忌等）
  - `relations.csv` — 关系三元组（HAS_SYMPTOM, TREATS, CAUSES 等）

### 步骤 2：数据清洗与标签对齐

CMeKG 的实体类型与项目当前类型需要对齐：

| CMeKG 类型 | 项目 Neo4j Label | 备注 |
|------------|-----------------|------|
| Disease | Disease | 直接映射 |
| Symptom | Symptom | 直接映射 |
| Drug | Drug | 直接映射 |
| Department | Condition | 科室归于 Condition |
| Check | Procedure | 检查归于 Procedure |

使用 `LABEL_MAP` 字典做映射，参考 `create_reference_links.py:13-18` 的模式。

### 步骤 3：生成 Embedding 并写入 Neo4j

复用项目现有的 `utils.py` 中的 `get_embedding()` （BGE-small-zh-v1.5, 512 维）。

写入脚本示例结构：

```python
# bottom_import.py
from n4j_shim import Neo4jGraph
from utils import get_embedding, str_uuid

def import_cmekg(entities_csv, relations_csv, n4j):
    gid = str_uuid()  # Bottom 层整体共享一个 gid 或每个子域一个

    # 1. 创建实体节点（MERGE 去重）
    for entity in entities:
        embedding = get_embedding(entity['name'] + entity.get('desc', ''))
        n4j.query("""
            MERGE (n:Disease {id: $id})
            SET n.name = $name, n.description = $desc,
                n.embedding = $emb, n.gid = $gid, n.layer = 'bottom'
        """, ...)

    # 2. 创建关系
    for rel in relations:
        n4j.query("""
            MATCH (a {id: $src}), (b {id: $tgt})
            MERGE (a)-[:HAS_SYMPTOM]->(b)
        """, ...)
```

### 步骤 4：创建 Bottom → Middle 的 REFERENCE 链接

复用 `create_reference_links.py` 的模式：
- 对每个 Bottom gid 计算其平均 embedding
- 计算与 Middle gid 平均 embedding 的余弦相似度
- 每个 Bottom gid 连 Top-K（K=10）最相似的 Middle Summary
- Threshold 建议 0.55（与现有 Middle→Top 链接一致）

修改 `create_reference_links.py` 的方向参数即可。

### 步骤 5：更新后端 GraphSearch

`graph_service.py` 的 Cypher 已支持 `layers` 参数过滤，无需修改。只需确保 Bottom 层节点写入时 `layer = 'bottom'` 即可自动参与跨层检索。

## 备选：LLM 从现有数据补全（无需外部数据源）

如果 CMeKG 不可用或质量不满足：

1. 遍历 Middle 层所有 Disease/Symptom 实体
2. 用 DeepSeek 批量生成 is-a 层次关系（如 "2型糖尿病 IS_A 糖尿病 IS_A 内分泌疾病"）
3. 用 DeepSeek 生成属性三元组（如 "糖尿病 HAS_CAUSE 胰岛素抵抗"）
4. 写入 Bottom 层并创建 REFERENCE 链接

这种方式的优势是不依赖外部数据，但 LLM 幻觉需人工抽检 5-10% 样本。

## 预计工作量

| 任务 | 预估耗时 |
|------|---------|
| CMeKG 数据下载与解析 | 0.5 天 |
| 数据清洗与标签对齐 | 1 天 |
| 导入脚本编写与测试 | 1 天 |
| REFERENCE 链接创建 | 0.5 天 |
| 端到端测试 | 0.5 天 |
| **合计** | **3-4 天** |

## 文件清单

- 修改：`create_reference_links.py`（增加 Bottom→Middle 方向）
- 新增：`bottom_import.py`（CMeKG 导入脚本）
- 可选新增：`bottom_bootstrap.py`（LLM 补全方案）
- 无需修改：`graph_service.py`、`backend/` 全部已兼容
