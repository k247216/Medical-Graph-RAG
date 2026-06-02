"""Neo4jGraph 兼容层 —— 用官方 neo4j driver 替代 CAMEL"""
from neo4j import GraphDatabase


class Neo4jGraph:
    def __init__(self, url: str, username: str, password: str):
        self._driver = GraphDatabase.driver(url, auth=(username, password))
        self._url = url

    def query(self, cypher: str, params: dict | None = None):
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            records = [record.data() for record in result]
        return records

    def close(self):
        self._driver.close()
