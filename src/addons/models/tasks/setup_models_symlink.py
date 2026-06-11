"""
SetupModelsSymlink Task - ensure the models symlink points at the data disk.
"""
from dataclasses import dataclass
from pathlib import Path

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class SetupModelsSymlinkTask(BaseTask):
    """Ensure `ComfyUI/models` points to the persistent models directory."""

    name: str = "SetupModelsSymlink"
    description: str = "Ensure ComfyUI/models points at the data disk"
    priority: int = 10

    MODELS_DIR_NAME: str = "models"

    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        return ctx.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)

    def _get_comfy_models_dir(self, ctx: AppContext) -> Path:
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            raise RuntimeError("ComfyUI directory is not initialized")
        return comfy_dir / self.MODELS_DIR_NAME

    def _setup_symlink(self, comfy_models: Path, target_models: Path) -> bool:
        """Create the symlink when it is missing or incorrect."""
        if not target_models.exists():
            target_models.mkdir(parents=True, exist_ok=True)
            logger.info(f"  -> 创建模型目录: {target_models}")

        if comfy_models.is_symlink():
            if comfy_models.resolve() == target_models.resolve():
                logger.info(f"  -> models 软链接已就绪 → {target_models}")
                return False

            logger.warning("  -> models 软链接指向错误，重建...")
            comfy_models.unlink()
        elif comfy_models.is_dir():
            logger.info("  -> 检测到 models 物理目录")
        elif comfy_models.exists():
            logger.warning("  -> [WARN] models 路径是文件，删除...")
            comfy_models.unlink()

        try:
            comfy_models.symlink_to(target_models)
            logger.info(f"  -> models 软链接已创建 → {target_models}")
            return True
        except OSError as e:
            logger.warning(f"  -> [SKIP] 无法创建软链接（可能需要管理员权限）: {e}")
            return False

    def execute(self, ctx: AppContext) -> TaskResult:
        logger.info(f"  -> [Task] {self.name}: 开始设置软链接...")

        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir or not comfy_dir.exists():
            logger.warning(f"  -> [Task] {self.name}: ComfyUI 目录不存在，跳过")
            return TaskResult.SKIPPED

        comfy_models = self._get_comfy_models_dir(ctx)
        target_models = self._get_target_models_dir(ctx)

        logger.info(f"  -> 目标模型目录: {target_models}")

        created = self._setup_symlink(comfy_models, target_models)
        return TaskResult.SUCCESS if created else TaskResult.SKIPPED
