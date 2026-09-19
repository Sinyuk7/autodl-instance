"""
MigrateExistingModels Task - migrate existing model files.

Move files from a physical `ComfyUI/models` directory into the persistent
models directory on the data disk, then rebuild the symlink when it is safe.
"""
import filecmp
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.addons.models.lock import EXCLUDED_EXTENSIONS
from src.core.file_migration import move_path_safely
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
    priority: int = 10

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

    def _unique_path(self, path: Path) -> Path:
        if not path.exists() and not path.is_symlink():
            return path
        index = 1
        while (
            path.with_name(f"{path.name}.{index}").exists()
            or path.with_name(f"{path.name}.{index}").is_symlink()
        ):
            index += 1
        return path.with_name(f"{path.name}.{index}")

    def _preserve_conflict(self, item: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        preserved = self._unique_path(destination)
        move_path_safely(item, preserved)
        logger.warning(f"  -> [WARN] 同名文件已保留至: {preserved}")

    def _migrate_directory_contents(
        self,
        src: Path,
        dst: Path,
        conflicts: Optional[Path] = None,
    ) -> MigrationStats:
        """Move contents recursively without overwriting persistent models."""
        stats = MigrationStats()
        conflicts = conflicts or (dst.parent / ".autodl-model-conflicts")

        if not src.exists() or not src.is_dir():
            return stats

        dst.mkdir(parents=True, exist_ok=True)
        for item in list(src.iterdir()):
            target = dst / item.name
            conflict = conflicts / item.name

            if item.is_symlink():
                if target.exists() or target.is_symlink():
                    self._preserve_conflict(item, conflict)
                    stats.model_conflicts += 1
                else:
                    move_path_safely(item, target)
                    stats.migrated += 1
                continue

            if item.is_file():
                if target.exists() or target.is_symlink():
                    if target.is_file() and filecmp.cmp(item, target, shallow=False):
                        item.unlink()
                        stats.auxiliary_conflicts += 1
                        continue
                    if self._is_auxiliary_file(item):
                        stats.auxiliary_conflicts += 1
                    else:
                        stats.model_conflicts += 1
                    self._preserve_conflict(item, conflict)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                move_path_safely(item, target)
                logger.info(f"  -> 迁移文件: {item.name}")
                stats.migrated += 1
                continue

            if item.is_dir():
                if target.exists() and (target.is_symlink() or not target.is_dir()):
                    self._preserve_conflict(item, conflict)
                    stats.model_conflicts += 1
                    continue

                target.mkdir(parents=True, exist_ok=True)
                child_stats = self._migrate_directory_contents(item, target, conflict)
                stats.migrated += child_stats.migrated
                stats.model_conflicts += child_stats.model_conflicts
                stats.auxiliary_conflicts += child_stats.auxiliary_conflicts

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

        if comfy_models.is_symlink():
            logger.error(
                f"  -> [ERROR] models 软链接指向意外位置，拒绝自动改写: {comfy_models}"
            )
            return TaskResult.FAILED

        if not comfy_models.is_dir():
            logger.info(f"  -> [Task] {self.name}: 无物理目录，跳过")
            return TaskResult.SKIPPED

        logger.info("  -> 开始迁移模型文件...")
        target_models.mkdir(parents=True, exist_ok=True)
        stats = self._migrate_directory_contents(comfy_models, target_models)

        if stats.auxiliary_conflicts:
            logger.info(
                f"  -> 处理 {stats.auxiliary_conflicts} 个已存在的辅助文件"
            )
        if stats.model_conflicts:
            logger.warning(
                f"  -> 检测到 {stats.model_conflicts} 个冲突，目标文件保持不变，源文件已单独保留"
            )

        comfy_models.rmdir()
        logger.info(f"  -> 已迁移 {stats.migrated} 个文件，删除原目录")

        try:
            comfy_models.symlink_to(target_models)
            return TaskResult.SUCCESS
        except OSError as e:
            logger.error(f"  -> [ERROR] 无法创建软链接: {e}")
            return TaskResult.FAILED
