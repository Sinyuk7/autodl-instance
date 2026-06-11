"""
MigrateExistingModels Task - migrate existing model files.

Move files from a physical `ComfyUI/models` directory into the persistent
models directory on the data disk, then rebuild the symlink when it is safe.
"""
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.addons.models.lock import EXCLUDED_EXTENSIONS
from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class MigrationStats:
    """Aggregate migration results for one directory tree."""

    migrated: int = 0
    model_conflicts: int = 0
    auxiliary_conflicts: int = 0


@dataclass
class MigrateExistingModelsTask(BaseTask):
    """Migrate model files from the ComfyUI tree into the data disk."""

    name: str = "MigrateExistingModels"
    description: str = "Migrate model files from ComfyUI into the data disk"
    priority: int = 20

    MODELS_DIR_NAME: str = "models"

    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        return ctx.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)

    def _get_comfy_models_dir(self, ctx: AppContext) -> Optional[Path]:
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            return None
        return comfy_dir / self.MODELS_DIR_NAME

    def _is_ready_symlink(self, comfy_models: Path, target_models: Path) -> bool:
        """Return True when the models path already points at the target."""
        return comfy_models.is_symlink() and comfy_models.resolve() == target_models.resolve()

    def _is_auxiliary_file(self, item: Path) -> bool:
        """Files that are safe to suppress from per-file conflict warnings."""
        if item.name.startswith("."):
            return True
        if item.name.startswith("put_") and item.name.endswith("_here"):
            return True
        if item.suffix.lower() in EXCLUDED_EXTENSIONS:
            return True
        return False

    def _dir_has_entries(self, path: Path) -> bool:
        return any(path.iterdir())

    def _migrate_directory_contents(self, src: Path, dst: Path) -> MigrationStats:
        """Move directory contents recursively, skipping conflicts."""
        stats = MigrationStats()

        if not src.exists() or not src.is_dir():
            return stats

        for item in src.iterdir():
            target = dst / item.name

            if item.is_file():
                if target.exists():
                    if self._is_auxiliary_file(item):
                        stats.auxiliary_conflicts += 1
                    else:
                        logger.warning(f"  -> [SKIP] 文件已存在，跳过: {item.name}")
                        stats.model_conflicts += 1
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(target))
                logger.info(f"  -> 迁移文件: {item.name}")
                stats.migrated += 1
                continue

            if item.is_dir():
                if not any(item.rglob("*")):
                    continue

                target.mkdir(parents=True, exist_ok=True)
                child_stats = self._migrate_directory_contents(item, target)
                stats.migrated += child_stats.migrated
                stats.model_conflicts += child_stats.model_conflicts
                stats.auxiliary_conflicts += child_stats.auxiliary_conflicts

                if item.exists() and item.is_dir() and not self._dir_has_entries(item):
                    item.rmdir()

        return stats

    def execute(self, ctx: AppContext) -> TaskResult:
        logger.info(f"  -> [Task] {self.name}: 检查需要迁移的文件...")

        comfy_models = self._get_comfy_models_dir(ctx)
        if not comfy_models:
            logger.info(f"  -> [Task] {self.name}: ComfyUI 目录不存在，跳过")
            return TaskResult.SKIPPED

        target_models = self._get_target_models_dir(ctx)

        if self._is_ready_symlink(comfy_models, target_models):
            logger.info(f"  -> [Task] {self.name}: models 软链接已就绪，无需迁移")
            return TaskResult.SKIPPED

        if not comfy_models.is_dir():
            logger.info(f"  -> [Task] {self.name}: 无物理目录，跳过")
            return TaskResult.SKIPPED

        if not self._dir_has_entries(comfy_models):
            logger.info(f"  -> [Task] {self.name}: 目录为空，跳过")
            return TaskResult.SKIPPED

        logger.info("  -> 开始迁移模型文件...")
        stats = self._migrate_directory_contents(comfy_models, target_models)

        if stats.auxiliary_conflicts:
            logger.info(
                f"  -> 跳过 {stats.auxiliary_conflicts} 个已存在的辅助文件"
            )
        if stats.model_conflicts:
            logger.warning(
                f"  -> 检测到 {stats.model_conflicts} 个同名模型文件，已保留目标目录中的现有文件"
            )

        if self._dir_has_entries(comfy_models):
            logger.info(
                f"  -> [Task] {self.name}: 存在未迁移的文件，保留物理目录"
            )
            return TaskResult.SKIPPED

        shutil.rmtree(comfy_models)
        logger.info(f"  -> 已迁移 {stats.migrated} 个文件，删除原目录")

        try:
            comfy_models.symlink_to(target_models)
            return TaskResult.SUCCESS
        except OSError as e:
            logger.warning(f"  -> [SKIP] 无法创建软链接: {e}")
            return TaskResult.SKIPPED
