"""
RAG 索引器 - 纯本地版本
使用 sentence-transformers 进行向量化，不需要任何 API
支持基于 Git 的增量索引
"""

import os
import json
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Chunk:
    """文档切片"""
    id: str
    content: str
    source_file: str
    start_line: int
    end_line: int
    metadata: Dict


@dataclass
class SearchResult:
    """搜索结果"""
    chunk: Chunk
    score: float
    
    def to_context(self) -> str:
        """转换为可复制的上下文格式"""
        return f"""--- 来源: {self.chunk.source_file} (行 {self.chunk.start_line}-{self.chunk.end_line}) [相关度: {self.score:.2f}] ---
{self.chunk.content}
"""


class RAGIndexer:
    """
    RAG 索引器
    
    功能：
    1. 扫描文档目录
    2. 切分文档为小块
    3. 使用本地模型向量化
    4. 搜索相关内容
    5. 输出可复制的上下文
    """
    
    def __init__(
        self,
        index_dir: str = ".rag_index",
        model_name: str = "all-MiniLM-L6-v2",  # 轻量级，约 80MB
        chunk_size: int = 500,  # 每块约 500 字符
        chunk_overlap: int = 50,  # 重叠 50 字符
    ):
        self.index_dir = Path(index_dir)
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        self.chunks: List[Chunk] = []
        self.embeddings = None
        self.model = None
        
    def _ensure_model(self):
        """延迟加载模型"""
        if self.model is None:
            try:
                import logging
                import warnings
                
                # 抑制 transformers 和 huggingface 的烦人日志与警告
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
                logging.getLogger("transformers").setLevel(logging.ERROR)
                logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
                warnings.filterwarnings("ignore", category=FutureWarning)
                warnings.filterwarnings("ignore", category=UserWarning)
                
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError(
                    "请安装 sentence-transformers:\n"
                    "pip install sentence-transformers"
                )
            print(f"加载 Embedding 模型: {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            print("模型加载完成！")
    
    def _get_file_hash(self, file_path: Path) -> str:
        """获取文件哈希，用于检测变化"""
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()
    
    # ==================== Git 增量索引相关方法 ====================
    
    def _get_git_root(self, directory: Path) -> Optional[Path]:
        """获取 Git 仓库根目录"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=directory,
                capture_output=True,
                text=True,
                check=True
            )
            return Path(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _get_current_commit(self, git_root: Path) -> Optional[str]:
        """获取当前 commit hash"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _get_changed_files(
        self, 
        git_root: Path, 
        from_commit: str, 
        to_commit: str = "HEAD"
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        获取两个 commit 之间变化的文件
        
        Returns:
            (added_files, modified_files, deleted_files)
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", from_commit, to_commit],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set(), set(), set()
        
        added = set()
        modified = set()
        deleted = set()
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            status = parts[0][0]  # 取第一个字符 (A, M, D, R, etc.)
            file_path = parts[-1]  # 重命名时取新文件名
            
            if status == 'A':
                added.add(file_path)
            elif status == 'M':
                modified.add(file_path)
            elif status == 'D':
                deleted.add(file_path)
            elif status == 'R':  # 重命名视为删除旧文件 + 添加新文件
                if len(parts) >= 3:
                    deleted.add(parts[1])
                added.add(parts[-1])
        
        return added, modified, deleted
    
    def _get_all_valid_files(self, directory: Path, extensions: List[str], exclude_dirs: List[str]) -> List[Path]:
        """获取所有有效文件，优先使用 Git 以尊重 .gitignore"""
        git_root = self._get_git_root(directory)
        valid_files = []
        
        if git_root:
            try:
                # 获取已追踪文件
                tracked = subprocess.run(["git", "ls-files"], cwd=git_root, capture_output=True, text=True, check=True).stdout.splitlines()
                # 获取未追踪但未被忽略的文件
                untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=git_root, capture_output=True, text=True, check=True).stdout.splitlines()
                
                for f in tracked + untracked:
                    if not f: continue
                    file_path = git_root / f
                    # 检查扩展名和排除目录
                    if file_path.suffix in extensions and not any(ex in Path(f).parts for ex in exclude_dirs):
                        if file_path.is_file():
                            valid_files.append(file_path)
                return valid_files
            except subprocess.CalledProcessError:
                pass # Fallback to rglob
        
        # Fallback: rglob
        for file_path in directory.rglob('*'):
            if any(excluded in file_path.parts for excluded in exclude_dirs):
                continue
            if file_path.suffix not in extensions:
                continue
            if file_path.is_file():
                valid_files.append(file_path)
        return valid_files

    def _get_uncommitted_changes(self, git_root: Path) -> Set[str]:
        """获取未提交的修改文件（包括 staged 和 unstaged）"""
        changed = set()
        
        try:
            # staged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
            changed.update(result.stdout.strip().split('\n'))
            
            # unstaged changes
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
            changed.update(result.stdout.strip().split('\n'))
            
            # untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
            changed.update(result.stdout.strip().split('\n'))
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # 移除空字符串
        changed.discard('')
        return changed
    
    def _save_index_with_git_info(self, commit_hash: str):
        """保存索引并记录 Git commit 信息"""
        import numpy as np
        
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 chunks 元数据
        chunks_data = [asdict(chunk) for chunk in self.chunks]
        with open(self.index_dir / "chunks.json", 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)
        
        # 保存向量
        if self.embeddings is not None:
            np.save(self.index_dir / "embeddings.npy", self.embeddings)
        
        # 保存配置（包含 Git 信息）
        config = {
            "model_name": self.model_name,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "git_commit": commit_hash,
            "indexed_at": datetime.now().isoformat(),
        }
        with open(self.index_dir / "config.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"索引已保存到: {self.index_dir}")
        print(f"📌 Git commit: {commit_hash[:8]}...")
    
    def _load_last_indexed_commit(self) -> Optional[str]:
        """加载上次索引时的 Git commit"""
        config_path = self.index_dir / "config.json"
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config.get("git_commit")
        except (json.JSONDecodeError, IOError):
            return None
    
    def incremental_index(
        self,
        directory: str = ".",
        extensions: List[str] = None,
        exclude_dirs: List[str] = None,
        force_full: bool = False
    ) -> Tuple[int, int, int]:
        """
        基于 Git 的增量索引
        
        只索引自上次索引以来发生变化的文件
        
        Args:
            directory: 要索引的目录
            extensions: 要包含的文件扩展名
            exclude_dirs: 要排除的目录名
            force_full: 强制全量重建
            
        Returns:
            (added_count, updated_count, removed_count) 变化统计
        """
        import numpy as np
        
        if extensions is None:
            extensions = ['.md', '.py', '.txt', '.yaml', '.yml', '.json']
        if exclude_dirs is None:
            # 默认排除 rag 自身目录，防止污染索引
            exclude_dirs = ['.git', '__pycache__', 'node_modules', '.rag_index', 'venv', '.venv', 'rag']
        
        directory = Path(directory).resolve()
        git_root = self._get_git_root(directory)
        
        if git_root is None:
            print("⚠️  未检测到 Git 仓库，执行全量索引...")
            self.index_directory(str(directory), extensions, exclude_dirs)
            return (len(self.chunks), 0, 0)
        
        current_commit = self._get_current_commit(git_root)
        last_commit = self._load_last_indexed_commit()
        
        # 检查是否需要全量索引
        if force_full or last_commit is None or not self.load_index():
            print("📦 执行全量索引...")
            return self._full_index_with_git(directory, extensions, exclude_dirs, current_commit)
        
        # 获取变化的文件
        added, modified, deleted = self._get_changed_files(git_root, last_commit, current_commit)
        uncommitted = self._get_uncommitted_changes(git_root)
        
        # 检查当前索引中是否存在已经被本地删除的文件（处理未追踪文件的删除）
        indexed_files = {chunk.source_file for chunk in self.chunks}
        local_deleted = set()
        for f in indexed_files:
            if not (git_root / f).exists():
                local_deleted.add(f)
        
        # 合并所有变化
        files_to_update = added | modified | uncommitted
        files_to_remove = deleted | local_deleted
        
        # 过滤出符合扩展名的文件
        files_to_update = {f for f in files_to_update if Path(f).suffix in extensions}
        files_to_remove = {f for f in files_to_remove if Path(f).suffix in extensions}
        
        # 过滤排除目录
        files_to_update = {f for f in files_to_update 
                          if not any(ex in Path(f).parts for ex in exclude_dirs)}
        files_to_remove = {f for f in files_to_remove 
                          if not any(ex in Path(f).parts for ex in exclude_dirs)}
        
        total_changes = len(files_to_update) + len(files_to_remove)
        
        if total_changes == 0:
            print("✅ 索引已是最新状态，无需更新")
            return (0, 0, 0)
        
        print(f"🔄 检测到变化:")
        print(f"   📝 需要更新: {len(files_to_update)} 个文件")
        print(f"   🗑️  需要删除: {len(files_to_remove)} 个文件")
        print()
        
        self._ensure_model()
        
        # 构建文件到 chunks 的索引
        file_to_chunk_indices = {}
        for i, chunk in enumerate(self.chunks):
            if chunk.source_file not in file_to_chunk_indices:
                file_to_chunk_indices[chunk.source_file] = []
            file_to_chunk_indices[chunk.source_file].append(i)
        
        # 找出需要删除的 chunk 索引
        indices_to_remove = set()
        for file_path in files_to_remove | files_to_update:
            if file_path in file_to_chunk_indices:
                indices_to_remove.update(file_to_chunk_indices[file_path])
        
        # 保留不变的 chunks 和 embeddings
        keep_mask = [i not in indices_to_remove for i in range(len(self.chunks))]
        new_chunks = [c for c, keep in zip(self.chunks, keep_mask) if keep]
        new_embeddings = self.embeddings[keep_mask] if self.embeddings is not None else None
        
        removed_count = len(indices_to_remove)
        print(f"   移除旧 chunks: {removed_count}")
        
        # 处理新增/修改的文件
        added_chunks = []
        for file_path in files_to_update:
            full_path = git_root / file_path
            if not full_path.exists() or not full_path.is_file():
                continue
            
            try:
                content = full_path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, IOError):
                continue
            
            if not content.strip():
                continue
            
            # 计算相对路径
            try:
                relative_path = str(full_path.relative_to(directory))
            except ValueError:
                relative_path = file_path
            
            chunks = self._split_into_chunks(content, relative_path)
            added_chunks.extend(chunks)
            print(f"   ✨ 索引: {relative_path} ({len(chunks)} 块)")
        
        # 生成新 chunks 的向量
        if added_chunks:
            print(f"\n生成向量 ({len(added_chunks)} 新块)...")
            texts = [chunk.content for chunk in added_chunks]
            new_chunk_embeddings = self.model.encode(texts, show_progress_bar=True)
            new_chunk_embeddings = np.array(new_chunk_embeddings)
            
            # 合并
            new_chunks.extend(added_chunks)
            if new_embeddings is not None and len(new_embeddings) > 0:
                new_embeddings = np.vstack([new_embeddings, new_chunk_embeddings])
            else:
                new_embeddings = new_chunk_embeddings
        
        self.chunks = new_chunks
        self.embeddings = new_embeddings
        
        # 保存更新后的索引
        self._save_index_with_git_info(current_commit)
        
        added_count = len(added_chunks)
        print(f"\n✅ 增量索引完成！")
        print(f"   📊 当前总计: {len(self.chunks)} 个文档块")
        print(f"   ➕ 新增: {added_count} 块")
        print(f"   ➖ 移除: {removed_count} 块")
        
        return (added_count, removed_count, 0)
    
    def _full_index_with_git(
        self,
        directory: Path,
        extensions: List[str],
        exclude_dirs: List[str],
        commit_hash: str
    ) -> Tuple[int, int, int]:
        """执行全量索引并记录 Git 信息"""
        import numpy as np
        
        self._ensure_model()
        all_chunks = []
        
        print(f"扫描目录: {directory}")
        
        valid_files = self._get_all_valid_files(directory, extensions, exclude_dirs)
        
        for file_path in valid_files:
            try:
                content = file_path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, IOError):
                continue
            
            if not content.strip():
                continue
            
            relative_path = str(file_path.relative_to(directory))
            chunks = self._split_into_chunks(content, relative_path)
            all_chunks.extend(chunks)
            print(f"  处理: {relative_path} ({len(chunks)} 块)")
        
        self.chunks = all_chunks
        
        if all_chunks:
            print(f"\n生成向量 ({len(all_chunks)} 块)...")
            texts = [chunk.content for chunk in all_chunks]
            self.embeddings = self.model.encode(texts, show_progress_bar=True)
            self.embeddings = np.array(self.embeddings)
        
        self._save_index_with_git_info(commit_hash)
        
        print(f"\n索引完成！共 {len(all_chunks)} 个文档块")
        return (len(all_chunks), 0, 0)
    
    def get_index_status(self) -> Dict:
        """获取索引状态信息"""
        config_path = self.index_dir / "config.json"
        
        if not config_path.exists():
            return {"status": "no_index", "message": "索引不存在"}
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"status": "error", "message": "无法读取配置"}
        
        # 检查 Git 状态
        git_root = self._get_git_root(Path("."))
        current_commit = self._get_current_commit(git_root) if git_root else None
        last_commit = config.get("git_commit")
        
        status = {
            "status": "ok",
            "indexed_at": config.get("indexed_at", "unknown"),
            "git_commit": last_commit[:8] if last_commit else None,
            "current_commit": current_commit[:8] if current_commit else None,
            "chunks_count": len(self.chunks) if self.chunks else "unknown",
        }
        
        if last_commit and current_commit:
            if last_commit == current_commit:
                status["git_status"] = "up_to_date"
                status["message"] = "索引与当前 commit 同步"
            else:
                # 计算变化
                added, modified, deleted = self._get_changed_files(git_root, last_commit, current_commit)
                uncommitted = self._get_uncommitted_changes(git_root)
                total = len(added) + len(modified) + len(deleted) + len(uncommitted)
                status["git_status"] = "outdated"
                status["message"] = f"有 {total} 个文件发生变化，建议运行增量索引"
                status["changes"] = {
                    "added": len(added),
                    "modified": len(modified),
                    "deleted": len(deleted),
                    "uncommitted": len(uncommitted)
                }
        
        return status
    
    # ==================== 原有方法 ====================
    
    def _split_into_chunks(self, content: str, source_file: str) -> List[Chunk]:
        """将文档切分为小块 (优化版：语言无关，优先在空行处切分)"""
        chunks = []
        lines = content.split('\n')
        
        current_chunk = []
        current_length = 0
        start_line = 1
        
        i = 0
        while i < len(lines):
            line = lines[i]
            current_chunk.append(line)
            current_length += len(line) + 1
            
            if current_length >= self.chunk_size:
                # 寻找最近的空行进行切断，避免生硬截断代码块或段落
                break_idx = len(current_chunk) - 1
                # 往回找最多 1/3 的 chunk 大小，看有没有空行
                search_limit = max(0, len(current_chunk) - (self.chunk_size // 3 // 40)) # 粗略估算行数
                
                for j in range(len(current_chunk) - 1, search_limit, -1):
                    if not current_chunk[j].strip():
                        break_idx = j
                        break
                
                # 截取到 break_idx
                actual_chunk = current_chunk[:break_idx + 1]
                chunk_content = '\n'.join(actual_chunk)
                end_line = start_line + len(actual_chunk) - 1
                
                if chunk_content.strip():
                    chunks.append(Chunk(
                        id=f"{source_file}:{start_line}-{end_line}",
                        content=chunk_content,
                        source_file=source_file,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={}
                    ))
                
                # 处理重叠部分
                overlap_lines = []
                overlap_length = 0
                for ln in reversed(actual_chunk):
                    if overlap_length + len(ln) > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, ln)
                    overlap_length += len(ln) + 1
                
                # 剩下的行放回下一次循环
                remains = current_chunk[break_idx + 1:]
                current_chunk = overlap_lines + remains
                current_length = overlap_length + sum(len(l) + 1 for l in remains)
                start_line = end_line - len(overlap_lines) + 1
                
            i += 1
        
        # 处理最后一块
        if current_chunk:
            chunk_content = '\n'.join(current_chunk)
            if chunk_content.strip():
                end_line = start_line + len(current_chunk) - 1
                chunks.append(Chunk(
                    id=f"{source_file}:{start_line}-{end_line}",
                    content=chunk_content,
                    source_file=source_file,
                    start_line=start_line,
                    end_line=end_line,
                    metadata={}
                ))
        
        return chunks
    
    def index_directory(
        self,
        directory: str,
        extensions: List[str] = None,
        exclude_dirs: List[str] = None
    ) -> int:
        """
        索引指定目录下的所有文档
        
        Args:
            directory: 要索引的目录
            extensions: 要包含的文件扩展名，默认 ['.md', '.py', '.txt', '.yaml']
            exclude_dirs: 要排除的目录名
            
        Returns:
            索引的文档块数量
        """
        if extensions is None:
            extensions = ['.md', '.py', '.txt', '.yaml', '.yml', '.json']
        if exclude_dirs is None:
            # 默认排除 rag 自身目录，防止污染索引
            exclude_dirs = ['.git', '__pycache__', 'node_modules', '.rag_index', 'venv', '.venv', 'rag']
        
        self._ensure_model()
        
        directory = Path(directory)
        all_chunks = []
        
        print(f"扫描目录: {directory}")
        
        valid_files = self._get_all_valid_files(directory, extensions, exclude_dirs)
        
        for file_path in valid_files:
            try:
                content = file_path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, IOError):
                continue
            
            # 跳过空文件
            if not content.strip():
                continue
            
            relative_path = str(file_path.relative_to(directory))
            chunks = self._split_into_chunks(content, relative_path)
            all_chunks.extend(chunks)
            print(f"  处理: {relative_path} ({len(chunks)} 块)")
        
        self.chunks = all_chunks
        
        # 生成向量
        if all_chunks:
            print(f"\n生成向量 ({len(all_chunks)} 块)...")
            import numpy as np
            texts = [chunk.content for chunk in all_chunks]
            self.embeddings = self.model.encode(texts, show_progress_bar=True)
            self.embeddings = np.array(self.embeddings)
        
        # 保存索引
        self._save_index()
        
        print(f"\n索引完成！共 {len(all_chunks)} 个文档块")
        return len(all_chunks)
    
    def _save_index(self):
        """保存索引到磁盘"""
        import numpy as np
        
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 chunks 元数据
        chunks_data = [asdict(chunk) for chunk in self.chunks]
        with open(self.index_dir / "chunks.json", 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)
        
        # 保存向量
        if self.embeddings is not None:
            np.save(self.index_dir / "embeddings.npy", self.embeddings)
        
        # 保存配置
        config = {
            "model_name": self.model_name,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }
        with open(self.index_dir / "config.json", 'w') as f:
            json.dump(config, f)
        
        print(f"索引已保存到: {self.index_dir}")
    
    def load_index(self) -> bool:
        """从磁盘加载索引"""
        import numpy as np
        
        chunks_path = self.index_dir / "chunks.json"
        embeddings_path = self.index_dir / "embeddings.npy"
        
        if not chunks_path.exists() or not embeddings_path.exists():
            return False
        
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        self.chunks = [Chunk(**data) for data in chunks_data]
        self.embeddings = np.load(embeddings_path)
        
        print(f"已加载索引: {len(self.chunks)} 个文档块")
        return True
    
    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        搜索与查询最相关的文档块
        
        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            
        Returns:
            搜索结果列表
        """
        import numpy as np
        
        self._ensure_model()
        
        if not self.chunks or self.embeddings is None:
            raise ValueError("索引为空，请先调用 index_directory() 或 load_index()")
        
        # 编码查询
        query_embedding = self.model.encode([query])[0]
        
        # 计算余弦相似度
        similarities = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # 获取 top_k 结果
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append(SearchResult(
                chunk=self.chunks[idx],
                score=float(similarities[idx])
            ))
        
        return results
    
    def search_and_format(self, query: str, top_k: int = 5) -> str:
        """
        搜索并格式化为可复制的上下文
        
        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            
        Returns:
            格式化的上下文字符串，可直接复制到 AI 对话
        """
        results = self.search(query, top_k)
        
        output_parts = [
            "=" * 60,
            f"🔍 查询: {query}",
            f"📚 找到 {len(results)} 个相关文档块",
            "=" * 60,
            "",
            "以下是从项目文档中检索到的相关内容，请基于这些内容回答问题：",
            "",
        ]
        
        for i, result in enumerate(results, 1):
            output_parts.append(f"【文档 {i}】")
            output_parts.append(result.to_context())
        
        output_parts.extend([
            "=" * 60,
            "💡 提示: 复制以上内容到你的 AI 对话中使用",
            "=" * 60,
        ])
        
        return '\n'.join(output_parts)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG 本地检索工具")
    parser.add_argument("command", choices=["index", "search"], help="命令: index 或 search")
    parser.add_argument("--dir", "-d", default=".", help="要索引的目录")
    parser.add_argument("--query", "-q", help="搜索查询")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="返回结果数量")
    parser.add_argument("--index-dir", default=".rag_index", help="索引存储目录")
    
    args = parser.parse_args()
    
    indexer = RAGIndexer(index_dir=args.index_dir)
    
    if args.command == "index":
        indexer.index_directory(args.dir)
    
    elif args.command == "search":
        if not args.query:
            print("错误: 搜索需要提供 --query 参数")
            return
        
        if not indexer.load_index():
            print("错误: 未找到索引，请先运行 index 命令")
            return
        
        result = indexer.search_and_format(args.query, args.top_k)
        print(result)


if __name__ == "__main__":
    main()
