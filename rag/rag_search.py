#!/usr/bin/env python3
"""
RAG 交互式检索工具
运行后可以持续输入问题，获取相关文档内容
支持基于 Git 的增量索引
"""

import sys
from pathlib import Path

# 添加 rag 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from rag_indexer import RAGIndexer


def print_status(indexer: RAGIndexer):
    """打印索引状态"""
    status = indexer.get_index_status()
    
    print("\n📊 索引状态:")
    print("-" * 40)
    
    if status["status"] == "no_index":
        print("❌ 索引不存在，请先运行 'reindex' 或 'update'")
        return
    
    print(f"   索引时间: {status.get('indexed_at', 'unknown')}")
    print(f"   文档块数: {status.get('chunks_count', 'unknown')}")
    
    if status.get("git_commit"):
        print(f"   索引 commit: {status['git_commit']}")
    if status.get("current_commit"):
        print(f"   当前 commit: {status['current_commit']}")
    
    if status.get("git_status") == "up_to_date":
        print("   ✅ 索引已是最新")
    elif status.get("git_status") == "outdated":
        print(f"   ⚠️  {status.get('message', '需要更新')}")
        if "changes" in status:
            changes = status["changes"]
            print(f"      新增: {changes.get('added', 0)} 文件")
            print(f"      修改: {changes.get('modified', 0)} 文件")
            print(f"      删除: {changes.get('deleted', 0)} 文件")
            print(f"      未提交: {changes.get('uncommitted', 0)} 文件")
    
    print("-" * 40)


def interactive_search():
    """交互式搜索模式"""
    indexer = RAGIndexer()
    
    # 加载或创建索引
    if not indexer.load_index():
        print("未找到索引，开始创建...")
        print()
        indexer.incremental_index(".")
        print()
    
    print("=" * 60)
    print("🔍 RAG 本地检索工具 (支持 Git 增量索引)")
    print("=" * 60)
    print("输入你的问题，按回车搜索")
    print()
    print("命令:")
    print("  quit / q     - 退出")
    print("  reindex      - 全量重建索引")
    print("  update       - 增量更新索引 (基于 Git)")
    print("  status       - 查看索引状态")
    print("=" * 60)
    print()
    
    while True:
        try:
            query = input("❓ 你的问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        
        if not query:
            continue
        
        if query.lower() in ('quit', 'q', 'exit'):
            print("再见！")
            break
        
        if query.lower() == 'reindex':
            print("\n📦 全量重建索引...")
            indexer.incremental_index(".", force_full=True)
            print()
            continue
        
        if query.lower() == 'update':
            print("\n🔄 增量更新索引...")
            indexer.incremental_index(".")
            print()
            continue
        
        if query.lower() == 'status':
            print_status(indexer)
            print()
            continue
        
        # 执行搜索
        result = indexer.search_and_format(query, top_k=5)
        print()
        print(result)
        print()
        
        # 复制提示
        print("📋 提示: 你可以复制上面的内容，粘贴到 AI 对话中")
        print()


if __name__ == "__main__":
    interactive_search()