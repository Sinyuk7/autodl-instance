"""
MigrateExistingModels Task - 迁移现有模型文件

迁移 ComfyUI 物理目录中的现有模型文件到数据盘。
"""
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class MigrateExistingModelsTask(BaseTask):
    """迁移现有模型文件 Task"""
    
    name: str = "MigrateExistingModels"
    description: str = "迁移 ComfyUI 物理目录中的模型到数据盘"
    priority: int = 20
    
    MODELS_DIR_NAME: str = "models"
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.base_dir / self.MODELS_DIR_NAME
    
    def _get_comfy_models_dir(self, ctx: AppContext) -> Optional[Path]:
        """获取 ComfyUI 的 models 目录路径"""
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            return None
        return comfy_dir / self.MODELS_DIR_NAME
    
    def _migrate_directory_contents(self, src: Path, dst: Path) -> int:
        """将 src 目录内容迁移到 dst，冲突时跳过
        
        Returns:
            迁移的文件数量
        """
        migrated = 0
        
        if not src.exists() or not src.is_dir():
            return migrated
        
        for item in src.iterdir():
            target = dst / item.name
            
            if item.is_file():
                if target.exists():
                    logger.warning(f"  -> [SKIP] 文件已存在，跳过: {item.name}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(target))
                    logger.info(f"  -> 迁移文件: {item.name}")
                    migrated += 1
            
            elif item.is_dir():
                # 跳过空目录
                if not any(item.rglob("*")):
                    continue
                # 递归迁移子目录
                target.mkdir(parents=True, exist_ok=True)
                migrated += self._migrate_directory_contents(item, target)
        
        return migrated
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """执行模型迁移"""
        logger.info(f"  -> [Task] {self.name}: 检查需要迁移的文件...")
        
        comfy_models = self._get_comfy_models_dir(ctx)
        if not comfy_models:
            logger.info(f"  -> [Task] {self.name}: ComfyUI 目录不存在，跳过")
            return TaskResult.SKIPPED
        
        target_models = self._get_target_models_dir(ctx)
        
        # 检查是否是物理目录（需要迁移）
        if not comfy_models.is_dir():
            logger.info(f"  -> [Task] {self.name}: 无物理目录，跳过")
            return TaskResult.SKIPPED
        
        # 检查目录是否为空
        if not any(comfy_models.rglob("*")):
            logger.info(f"  -> [Task] {self.name}: 目录为空，跳过")
            return TaskResult.SKIPPED
        
        logger.info(f"  -> 开始迁移模型文件...")
        migrated = self._migrate_directory_contents(comfy_models, target_models)
        
        if migrated > 0:
            # 删除原目录
            shutil.rmtree(comfy_models)
            logger.info(f"  -> 已迁移 {migrated} 个文件，删除原目录")
        
        # 重建软链接
        try:
            comfy_models.symlink_to(target_models)
            logger.info(f"  -> [Task] {self.name}: 完成 ✓")
            return TaskResult.SUCCESS
        except OSError as e:
            logger.warning(f"  -> [SKIP] 无法创建软链接: {e}")
            return TaskResult.SKIPPED