"""
GenerateSnapshot Task - 生成模型快照

扫描模型目录，生成 model-lock.yaml 快照。
"""
from dataclasses import dataclass
from pathlib import Path

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger
from src.addons.models.config import get_legacy_lock_file, get_lock_file
from src.addons.models.lock import generate_snapshot
from src.lib.utils import load_yaml, save_yaml


@dataclass
class GenerateSnapshotTask(BaseTask):
    """生成模型快照 Task"""
    
    name: str = "GenerateSnapshot"
    description: str = "生成 model-lock.yaml 快照"
    priority: int = 30
    
    MODELS_DIR_NAME: str = "models"
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.artifacts.models_dir or ctx.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)
    
    def _get_lock_file_path(self, ctx: AppContext) -> Path:
        """获取 lock 文件路径"""
        return get_lock_file(ctx.userdata_dir)

    def _load_previous_lock(self, ctx: AppContext) -> dict:
        """加载新路径 lock；缺失时兼容读取旧数据盘根目录 lock。"""
        lock_file = self._get_lock_file_path(ctx)
        if lock_file.exists():
            return load_yaml(lock_file)

        legacy_lock = get_legacy_lock_file(ctx.base_dir)
        if legacy_lock.exists():
            logger.info(f"  -> [Task] {self.name}: 检测到旧 lock，作为增量基线读取: {legacy_lock}")
            return load_yaml(legacy_lock)

        return {}
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """生成快照"""
        logger.info(f"  -> [Task] {self.name}: 扫描模型目录...")
        
        models_dir = self._get_target_models_dir(ctx)
        
        if not models_dir.exists():
            logger.info(f"  -> [Task] {self.name}: 模型目录不存在，跳过")
            return TaskResult.SKIPPED
        
        lock_file = self._get_lock_file_path(ctx)
        previous_lock = self._load_previous_lock(ctx)
        
        # 生成快照
        snapshot = generate_snapshot(models_dir, previous_lock)
        
        model_count = len(snapshot.get("models", []))
        if model_count == 0:
            logger.info(f"  -> [Task] {self.name}: 目录为空，跳过")
            return TaskResult.SKIPPED
        
        # 写入 lock 文件
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(lock_file, snapshot)
        
        logger.info(f"  -> [Task] {self.name}: 完成 ✓ ({model_count} 个模型)")
        return TaskResult.SUCCESS
