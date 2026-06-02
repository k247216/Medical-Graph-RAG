# Neo4j 数据库文件

此目录存放 Neo4j 数据库文件，因体积过大（~1GB）不纳入 Git。

## 目录结构

```
neo4j-data/
├── data/       ← 放入 Neo4j 数据库文件（联系项目负责人获取）
├── logs/       ← Neo4j 自动生成
└── import/     ← 可选，用于 neo4j-admin import
```

## 获取数据

联系项目负责人获取 `neo4j-data.tar.gz`，解压到此目录：

```bash
tar -xzf neo4j-data.tar.gz -C neo4j-data/
```

## 验证

```bash
ls neo4j-data/data/databases/neo4j/
# 应看到 neostore.* 等数据库文件

docker compose up -d neo4j
# 浏览器打开 http://localhost:7474 验证
```
