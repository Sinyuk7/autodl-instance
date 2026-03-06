"""
CleanupOrphanMetas Task - 清理孤儿 .meta 文件

清理没有对应模型文件的 .meta sidecar 文件。
"""
from dataclasses import dataclass
from pathlib import Path

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class CleanupOrphanMetasTask(BaseTask):
    """清理孤儿 .meta 文件 Task"""
    
    name: str = "CleanupOrphanMetas"
    description: str = "清理孤儿 .meta sidecar 文件"
    priority: int = 20
    
    MODELS_DIR_NAME: str = "models"
    META_SUFFIX: str = ".meta"
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.artifacts.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)
    
    def _cleanup(self, models_base: Path) -> int:
        """清理孤儿 .meta 文件
        
        Returns:
            清理的文件数量
        """
        cleaned = 0
        
        if not models_base.exists():
            return cleaned
        
        for meta_file in models_base.rglob(f".*{self.META_SUFFIX}"):
            if not meta_file.is_file():
                continue
            
            # .flux.safetensors.meta -> flux.safetensors
            model_name = meta_file.name[1:]  # 去掉开头的 .
            if model_name.endswith(self.META_SUFFIX):
                model_name = model_name[:-len(self.META_SUFFIX)]
            
            model_file = meta_file.parent / model_name
            if not model_file.exists():
                try:
                    meta_file.unlink()
                    logger.info(f"  -> 清理孤儿 meta: {meta_file.name}")
                    cleaned += 1
                except OSError:
                    pass
        
        return cleaned
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """执行清理"""
        logger.info(f"  -> [Task] {self.name}: 检查孤儿 .meta 文件...")
        
        models_dir = self._get_target_models_dir(ctx)
        
        if not models_dir.exists():
            logger.info(f"  -> [Task] {self.name}: 模型目录不存在，跳过")
            return TaskResult.SKIPPED
        
        cleaned = self._cleanup(models_dir)
        
        if cleaned > 0:
            logger.info(f"  -> [Task] {self.name}: 完成 ✓ (清理 {cleaned} 个文件)")
            return TaskResult.SUCCESS
        else:
            logger.info(f"  -> [Task] {self.name}: 跳过 (无孤儿文件)")
            return TaskResult.SKIPPED