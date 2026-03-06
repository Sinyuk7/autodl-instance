"""
GenerateSnapshot Task - 生成模型快照

扫描模型目录，生成 model-lock.yaml 快照。
"""
from dataclasses import dataclass
from pathlib import Path

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger
from src.lib.utils import load_yaml, save_yaml


@dataclass
class GenerateSnapshotTask(BaseTask):
    """生成模型快照 Task"""
    
    name: str = "GenerateSnapshot"
    description: str = "生成 model-lock.yaml 快照"
    priority: int = 30
    
    MODELS_DIR_NAME: str = "models"
    LOCK_FILE_NAME: str = "model-lock.yaml"
    
    # 排除的文件扩展名
    EXCLUDED_EXTENSIONS: tuple = (
        ".yaml", ".yml", ".json", ".txt", ".md", ".log",
        ".py", ".sh", ".bat", ".ps1",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
        ".html", ".css", ".js",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".lock", ".metadata", ".meta",
    )
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.artifacts.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)
    
    def _get_lock_file_path(self, ctx: AppContext) -> Path:
        """获取 lock 文件路径"""
        return ctx.base_dir / self.LOCK_FILE_NAME
    
    def _scan_models(self, models_base: Path) -> list:
        """扫描模型文件"""
        results = []
        
        if not models_base.exists():
            return results
        
        for model_file in sorted(models_base.rglob("*")):
            if not model_file.is_file():
                continue
            # 跳过隐藏文件
            if model_file.name.startswith("."):
                continue
            # 跳过隐藏目录下的文件
            rel_parts = model_file.relative_to(models_base).parts
            if any(part.startswith(".") for part in rel_parts[:-1]):
                continue
            # 跳过非模型文件
            if model_file.suffix.lower() in self.EXCLUDED_EXTENSIONS:
                continue
            # 跳过 0 字节文件
            if model_file.stat().st_size == 0:
                continue
            # 跳过占位文件
            if model_file.name.startswith("put_") and model_file.name.endswith("_here"):
                continue
            
            rel_path = model_file.relative_to(models_base).as_posix()
            parts = rel_path.split("/")
            model_type = parts[0] if len(parts) > 1 else None
            
            results.append({
                "path": rel_path,
                "size": model_file.stat().st_size,
                "type": model_type,
            })
        
        return results
    
    def _generate_snapshot(
        self,
        models_base: Path,
        previous_lock: dict
    ) -> dict:
        """生成快照"""
        from datetime import datetime, timezone
        from src.lib.utils import sha256
        
        # 构建上一次 lock 的索引
        prev_index = {}
        for m in previous_lock.get("models", []):
            path = m.get("paths", [{}])[0].get("path", "")
            if path:
                prev_index[path] = m
        
        # 扫描当前文件
        scanned = self._scan_models(models_base)
        
        models = []
        for item in scanned:
            rel_path = item["path"]
            file_path = models_base / rel_path
            
            # 增量 hash
            prev = prev_index.get(rel_path)
            existing_hash = None
            
            if prev:
                prev_hashes = prev.get("hashes", [])
                if prev_hashes:
                    existing_hash = prev_hashes[0].get("hash")
                prev_size = prev.get("_size")
                prev_mtime = prev.get("_mtime")
                if prev_size == item["size"] and prev_mtime == item.get("mtime") and existing_hash:
                    file_hash = existing_hash
                else:
                    file_hash = sha256(file_path)
            else:
                file_hash = sha256(file_path)
            
            entry = {
                "model": file_path.stem,
                "paths": [{"path": rel_path}],
                "hashes": [{"hash": file_hash, "type": "SHA256"}],
                "_size": item["size"],
                "_mtime": item.get("mtime"),
            }
            if item.get("type"):
                entry["type"] = item["type"]
            
            models.append(entry)
        
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": models,
        }
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """生成快照"""
        logger.info(f"  -> [Task] {self.name}: 扫描模型目录...")
        
        models_dir = self._get_target_models_dir(ctx)
        
        if not models_dir.exists():
            logger.info(f"  -> [Task] {self.name}: 模型目录不存在，跳过")
            return TaskResult.SKIPPED
        
        # 加载上一次 lock
        lock_file = self._get_lock_file_path(ctx)
        previous_lock = load_yaml(lock_file) if lock_file.exists() else {}
        
        # 生成快照
        snapshot = self._generate_snapshot(models_dir, previous_lock)
        
        model_count = len(snapshot.get("models", []))
        if model_count == 0:
            logger.info(f"  -> [Task] {self.name}: 目录为空，跳过")
            return TaskResult.SKIPPED
        
        # 写入 lock 文件
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(lock_file, snapshot)
        
        logger.info(f"  -> [Task] {self.name}: 完成 ✓ ({model_count} 个模型)")
        return TaskResult.SUCCESS