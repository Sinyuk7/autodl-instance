"""
SetupModelsSymlink Task - 建立 models 软链接

确保 ComfyUI/models/ 软链接指向数据盘 autodl-tmp/models/。
"""
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class SetupModelsSymlinkTask(BaseTask):
    """建立 models 软链接 Task"""
    
    name: str = "SetupModelsSymlink"
    description: str = "确保 ComfyUI/models/ 软链接指向数据盘"
    priority: int = 10
    
    MODELS_DIR_NAME: str = "models"
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.base_dir / self.MODELS_DIR_NAME
    
    def _get_comfy_models_dir(self, ctx: AppContext) -> Path:
        """获取 ComfyUI 的 models 目录路径"""
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            raise RuntimeError("ComfyUI 目录未初始化")
        return comfy_dir / self.MODELS_DIR_NAME
    
    def _setup_symlink(self, comfy_models: Path, target_models: Path) -> bool:
        """创建软链接
        
        Returns:
            True 如果创建了新链接
        """
        # 确保目标目录存在
        if not target_models.exists():
            target_models.mkdir(parents=True, exist_ok=True)
            logger.info(f"  -> 创建模型目录: {target_models}")
        
        # Case 1: 已是正确的软链接
        if comfy_models.is_symlink():
            if comfy_models.resolve() == target_models.resolve():
                logger.info(f"  -> models 软链接已就绪 → {target_models}")
                return False
            else:
                # 软链接指向错误位置，删除重建
                logger.warning(f"  -> models 软链接指向错误，重建...")
                comfy_models.unlink()
        
        # Case 2: 是物理目录
        elif comfy_models.is_dir():
            logger.info(f"  -> 检测到 models 物理目录")
        
        # Case 3: 路径不存在或是文件
        elif comfy_models.exists():
            logger.warning(f"  -> [WARN] models 路径是文件，删除...")
            comfy_models.unlink()
        
        # 创建软链接
        try:
            comfy_models.symlink_to(target_models)
            logger.info(f"  -> models 软链接已创建 → {target_models}")
            return True
        except OSError as e:
            logger.warning(f"  -> [SKIP] 无法创建软链接（需管理员权限）: {e}")
            return False
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """执行软链接设置"""
        logger.info(f"  -> [Task] {self.name}: 开始设置软链接...")
        
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir or not comfy_dir.exists():
            logger.warning(f"  -> [Task] {self.name}: ComfyUI 目录不存在，跳过")
            return TaskResult.SKIPPED
        
        comfy_models = self._get_comfy_models_dir(ctx)
        target_models = self._get_target_models_dir(ctx)
        
        logger.info(f"  -> 目标模型目录: {target_models}")
        
        created = self._setup_symlink(comfy_models, target_models)
        
        if created:
            logger.info(f"  -> [Task] {self.name}: 完成 ✓")
            return TaskResult.SUCCESS
        else:
            logger.info(f"  -> [Task] {self.name}: 跳过 (已就绪)")
            return TaskResult.SKIPPED