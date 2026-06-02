"""
三层架构导入脚本
完整实现论文的三层架构：Bottom/Middle/Top
"""

import json
import os
import sys
import asyncio
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from n4j_shim import Neo4jGraph
from dataloader import load_high
from creat_graph_with_description import creat_metagraph_with_description
from utils import str_uuid, ref_link

MAX_CONCURRENT = 12


class ThreeLayerImporter:
    """三层架构导入器"""

    def __init__(self, neo4j_url, neo4j_username, neo4j_password):
        """初始化"""
        print("\n" + "="*80)
        print("三层架构知识图谱导入器")
        print("="*80)

        # 连接 Neo4j
        print("\n[连接Neo4j]...")
        self.n4j = Neo4jGraph(
            url=neo4j_url,
            username=neo4j_username,
            password=neo4j_password
        )
        print("✅ Neo4j连接成功")

        # 存储每层的 GID
        self.layer_gids = {
            'bottom': [],
            'middle': [],
            'top': []
        }
        self._lock = asyncio.Lock()
        self._cp_lock = threading.Lock()
        self._completed = 0
        self._total = 0
        self._processed_files: set = set()
        self._processed_gids: dict = {}

    def clear_database(self):
        """清空数据库（自动清空，无需确认）"""
        print("\n[清空数据库]...")
        result = self.n4j.query("MATCH (n) RETURN count(n) as count")
        count = result[0]['count'] if result else 0
        print(f"当前节点数: {count}")

        if count > 0:
            print("自动清空数据库...")
            self.n4j.query("MATCH (n) DETACH DELETE n")
            print("✅ 数据库已清空")
        else:
            print("数据库已经是空的")

        # 同时清空 checkpoint
        for layer in ['bottom', 'middle', 'top']:
            cp = Path(f"data/.import_checkpoint_{layer}.json")
            if cp.exists():
                cp.unlink()
                print(f"  已删除 checkpoint: {cp.name}")

    def _checkpoint_path(self, layer_name: str) -> Path:
        return Path(f"data/.import_checkpoint_{layer_name}.json")

    def _load_checkpoint(self, layer_name: str) -> tuple[set, dict]:
        cp = self._checkpoint_path(layer_name)
        if cp.exists():
            try:
                data = json.loads(cp.read_text())
                return set(data.get("files", [])), data.get("gids", {})
            except (json.JSONDecodeError, KeyError):
                pass
        return set(), {}

    def _save_checkpoint(self, layer_name: str, processed_files: set, processed_gids: dict):
        cp = self._checkpoint_path(layer_name)
        with self._cp_lock:
            cp.write_text(json.dumps({
                "files": sorted(processed_files),
                "gids": processed_gids
            }))

    def _process_one_file(self, file_path: Path, idx: int, layer_name: str, args) -> bool:
        """处理单个文件（同步，在 executor 线程中运行）"""
        fp_str = str(file_path)
        try:
            content = load_high(fp_str)

            if not content or len(content.strip()) < 50:
                print(f"  ⏭️  [{idx}/{self._total}] 跳过(太短): {file_path.name}")
                # 太短的文件也标记为已处理，避免每次重试
                self._processed_files.add(fp_str)
                self._save_checkpoint(layer_name, self._processed_files, self._processed_gids)
                return False

            gid = str_uuid()

            # 创建图谱
            creat_metagraph_with_description(args, content, gid, self.n4j)

            # 写入 layer 属性
            set_layer_query = """
            MATCH (n)
            WHERE n.gid = $gid AND NOT n:Summary
            SET n.layer = $layer
            RETURN count(n) AS updated
            """
            result = self.n4j.query(set_layer_query, {'gid': gid, 'layer': layer_name})
            updated = result[0]['updated'] if result else 0

            self.layer_gids[layer_name].append(gid)
            self._processed_files.add(fp_str)
            self._processed_gids[fp_str] = gid
            self._save_checkpoint(layer_name, self._processed_files, self._processed_gids)

            print(f"  ✅ [{idx}/{self._total}] {file_path.name} ({updated} nodes)")
            return True

        except Exception as e:
            print(f"  ❌ [{idx}/{self._total}] {file_path.name}: {e}")
            return False

    async def import_layer(self, layer_name: str, data_path: str, args):
        """
        导入一个层的数据（并行处理，支持断点续传）

        Args:
            layer_name: 层名称 (bottom/middle/top)
            data_path: 数据路径
            args: 其他参数
        """
        print("\n" + "="*80)
        print(f"[{layer_name.upper()}层] 开始导入（并行: {MAX_CONCURRENT} 并发）")
        print(f"数据路径: {data_path}")
        print("="*80)

        data_path = Path(data_path)

        # 获取所有文本文件
        if data_path.is_file():
            files = [data_path]
        else:
            files = list(data_path.glob("*.txt"))
            files.extend(data_path.rglob("*/*.txt"))

        print(f"\n找到 {len(files)} 个文件")

        # 加载 checkpoint，过滤已处理文件
        processed, gids = self._load_checkpoint(layer_name)
        self._processed_files = processed
        self._processed_gids = gids
        self.layer_gids[layer_name] = list(gids.values())

        unprocessed = [(i, fp) for i, fp in enumerate(files, 1) if str(fp) not in processed]

        skipped = len(files) - len(unprocessed)
        if skipped > 0:
            print(f"已处理: {skipped} 个文件（从 checkpoint 恢复）")

        self._total = len(unprocessed)
        if self._total == 0:
            print("✅ 所有文件已处理完成，无需继续")
            return

        print(f"待处理: {self._total} 个文件\n")

        # 创建任务列表
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def bounded(idx: int, fp: Path):
            async with semaphore:
                loop = asyncio.get_running_loop()
                # idx 用原始文件序号，方便追踪
                return await loop.run_in_executor(
                    self._executor,
                    self._process_one_file, fp, idx, layer_name, args
                )

        self._executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
        tasks = [bounded(i, fp) for i, fp in unprocessed]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        self._executor.shutdown(wait=False)

        success = sum(1 for r in results if r is True)
        total = skipped + self._total

        print(f"\n{'='*80}")
        print(f"[{layer_name.upper()}层] 导入完成")
        print(f"本次: {success}/{self._total}, 累计: {len(self._processed_files)}/{total}, 共 {len(self.layer_gids[layer_name])} 个子图")
        print(f"{'='*80}")
    
    def create_trinity_links(self):
        """创建三层之间的 REFERENCE 关系"""
        print("\n" + "="*80)
        print("[Trinity链接] 开始创建跨层关系")
        print("="*80)
        
        total_links = 0
        
        # Bottom -> Middle
        print("\n[链接] Bottom → Middle")
        for bottom_gid in self.layer_gids['bottom']:
            for middle_gid in self.layer_gids['middle']:
                try:
                    result = ref_link(self.n4j, bottom_gid, middle_gid)
                    if result:
                        count = len(result)
                        total_links += count
                        if count > 0:
                            print(f"  ✅ {bottom_gid[:8]}... → {middle_gid[:8]}...: {count} 条")
                except Exception as e:
                    print(f"  ⚠️  错误: {e}")
        
        # Middle -> Top
        print("\n[链接] Middle → Top")
        for middle_gid in self.layer_gids['middle']:
            for top_gid in self.layer_gids['top']:
                try:
                    result = ref_link(self.n4j, middle_gid, top_gid)
                    if result:
                        count = len(result)
                        total_links += count
                        if count > 0:
                            print(f"  ✅ {middle_gid[:8]}... → {top_gid[:8]}...: {count} 条")
                except Exception as e:
                    print(f"  ⚠️  错误: {e}")
        
        print(f"\n{'='*80}")
        print(f"[Trinity链接] 完成")
        print(f"共创建 {total_links} 条 REFERENCE 关系")
        print(f"{'='*80}")
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*80)
        print("[统计信息]")
        print("="*80)
        
        # 节点统计
        result = self.n4j.query("MATCH (n) WHERE NOT n:Summary RETURN count(n) as count")
        node_count = result[0]['count'] if result else 0
        
        # Summary 统计
        result = self.n4j.query("MATCH (s:Summary) RETURN count(s) as count")
        summary_count = result[0]['count'] if result else 0
        
        # 关系统计
        result = self.n4j.query("MATCH ()-[r]->() RETURN count(r) as count")
        rel_count = result[0]['count'] if result else 0
        
        # REFERENCE 统计
        result = self.n4j.query("MATCH ()-[r:REFERENCE]->() RETURN count(r) as count")
        ref_count = result[0]['count'] if result else 0
        
        # 实体类型统计
        result = self.n4j.query("""
            MATCH (n)
            WHERE NOT n:Summary
            RETURN labels(n)[0] as type, count(n) as count
            ORDER BY count DESC
            LIMIT 10
        """)
        
        print(f"\n总体统计:")
        print(f"  - 实体节点: {node_count}")
        print(f"  - Summary节点: {summary_count}")
        print(f"  - 总关系: {rel_count}")
        print(f"  - REFERENCE关系: {ref_count}")
        
        print(f"\n层级统计:")
        print(f"  - Bottom层: {len(self.layer_gids['bottom'])} 个子图")
        print(f"  - Middle层: {len(self.layer_gids['middle'])} 个子图")
        print(f"  - Top层: {len(self.layer_gids['top'])} 个子图")
        
        print(f"\n实体类型 (前10):")
        for item in result:
            print(f"  - {item['type']}: {item['count']}")
        
        print(f"\n{'='*80}")


async def _run_imports(importer, args):
    """异步运行所有层的导入"""
    if args.bottom:
        await importer.import_layer('bottom', args.bottom, args)

    if args.middle:
        await importer.import_layer('middle', args.middle, args)

    if args.top:
        await importer.import_layer('top', args.top, args)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='三层架构知识图谱导入')

    # 数据路径
    parser.add_argument('--bottom', type=str, help='Bottom层数据路径（医学词典）')
    parser.add_argument('--middle', type=str, help='Middle层数据路径（诊疗指南）')
    parser.add_argument('--top', type=str, help='Top层数据路径（病例）')

    # 功能开关
    parser.add_argument('--clear', action='store_true', help='清空数据库')
    parser.add_argument('--trinity', action='store_true', help='创建Trinity关系')
    parser.add_argument('--grained_chunk', action='store_true', help='使用细粒度分块')
    parser.add_argument('--ingraphmerge', action='store_true', help='图内合并相似节点')

    # Neo4j 配置
    parser.add_argument('--neo4j-url', type=str,
                       default=os.getenv('NEO4J_URI', 'bolt://localhost:7687'))
    parser.add_argument('--neo4j-username', type=str,
                       default=os.getenv('NEO4J_USERNAME', 'neo4j'))
    parser.add_argument('--neo4j-password', type=str,
                       default=os.getenv('NEO4J_PASSWORD'))

    args = parser.parse_args()

    # 检查 Neo4j 密码
    if not args.neo4j_password:
        print("❌ 错误: 未提供 Neo4j 密码")
        print("请设置环境变量 NEO4J_PASSWORD 或使用 --neo4j-password 参数")
        sys.exit(1)

    # 初始化导入器
    importer = ThreeLayerImporter(
        args.neo4j_url,
        args.neo4j_username,
        args.neo4j_password
    )

    # 清空数据库
    if args.clear:
        importer.clear_database()

    # 异步导入各层
    asyncio.run(_run_imports(importer, args))

    # 创建 Trinity 关系
    if args.trinity:
        importer.create_trinity_links()

    # 打印统计
    importer.print_statistics()

    print("\n🎉 所有任务完成！")


if __name__ == '__main__':
    main()

