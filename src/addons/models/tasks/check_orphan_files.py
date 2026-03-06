"""
CheckOrphanFiles Task - 检查并迁移残留文件

检查并迁移可能残留在 ComfyUI 物理目录中的文件。
"""
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class CheckOrphanFilesTask(BaseTask):
    """检查并迁移残留文件 Task"""
    
    name: str = "CheckOrphanFiles"
    description: str = "检查并迁移 ComfyUI 物理目录中的残留文件"
    priority: int = 10
    
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
        """将 src 目录内容迁移到 dst，冲突时跳过"""
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
                if not any(item.rglob("*")):
                    continue
                target.mkdir(parents=True, exist_ok=True)
                migrated += self._migrate_directory_contents(item, target)
        
        return migrated
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """执行残留文件检查"""
        logger.info(f"  -> [Task] {self.name}: 检查残留文件...")
        
        comfy_models = self._get_comfy_models_dir(ctx)
        if not comfy_models:
            logger.info(f"  -> [Task] {self.name}: ComfyUI 目录不存在，跳过")
            return TaskResult.SKIPPED
        
        target_models = self._get_target_models_dir(ctx)
        
        # 如果是正确的软链接，无需处理
        if comfy_models.is_symlink():
            if comfy_models.resolve() == target_models.resolve():
                logger.info(f"  -> [Task] {self.name}: 软链接正常，跳过")
                return TaskResult.SKIPPED
            # 软链接指向错误，重建
            logger.warning(f"  -> [WARN] models 软链接指向错误，重建...")
            comfy_models.unlink()
            comfy_models.symlink_to(target_models)
            return TaskResult.SKIPPED
        
        # 如果变成了物理目录，迁移内容
        if comfy_models.is_dir():
            logger.info(f"  -> [WARN] 检测到 models 变为物理目录，迁移残留文件...")
            migrated = self._migrate_directory_contents(comfy_models, target_models)
            
            # 删除并重建软链接
            shutil.rmtree(comfy_models)
            comfy_models.symlink_to(target_models)
            logger.info(f"  -> 已重建 models 软链接")
            
            if migrated > 0:
                logger.info(f"  -> [Task] {self.name}: 完成 ✓ (迁移 {migrated} 个文件)")
                return TaskResult.SUCCESS
            else:
                logger.info(f"  -> [Task] {self.name}: 完成 ✓ (无需迁移)")
                return TaskResult.SUCCESS
        
        logger.info(f"  -> [Task] {self.name}: 跳过")
        return TaskResult.SKIPPED