"""Keep ComfyUI working data on the AutoDL data disk.

This is deliberately local-only: no remote repository or upload workflow is
involved.
"""
import filecmp
from pathlib import Path
from typing import List, cast

from src.core.file_migration import move_path_safely
from src.core.interface import AppContext, BaseAddon, hookimpl
from src.core.runtime import require_managed_storage_mount
from src.core.utils import logger


class WorkspaceAddon(BaseAddon):
    module_dir = "workspace"

    def _path_exists(self, path: Path) -> bool:
        return path.exists() or path.is_symlink()

    def _unique_path(self, path: Path) -> Path:
        if not self._path_exists(path):
            return path
        index = 1
        while self._path_exists(path.with_name(f"{path.name}.{index}")):
            index += 1
        return path.with_name(f"{path.name}.{index}")

    def _preserve_conflict(self, source: Path, conflict_path: Path) -> None:
        conflict_path.parent.mkdir(parents=True, exist_ok=True)
        destination = self._unique_path(conflict_path)
        move_path_safely(source, destination)
        logger.warning("  -> [WARN] 冲突文件已保留: %s", destination)

    def _merge_directory(self, source: Path, target: Path, conflicts: Path) -> None:
        """Merge without overwriting the persistent target."""
        target.mkdir(parents=True, exist_ok=True)
        for item in list(source.iterdir()):
            destination = target / item.name
            conflict = conflicts / item.name
            destination_exists = self._path_exists(destination)

            if item.is_symlink():
                if (
                    destination.is_symlink()
                    and item.resolve() == destination.resolve()
                ):
                    item.unlink()
                elif destination_exists:
                    self._preserve_conflict(item, conflict)
                else:
                    move_path_safely(item, destination)
                continue

            if item.is_dir():
                if destination_exists and (destination.is_symlink() or not destination.is_dir()):
                    self._preserve_conflict(item, conflict)
                    continue
                self._merge_directory(item, destination, conflict)
                item.rmdir()
                continue

            if destination_exists:
                if (
                    item.is_file()
                    and destination.is_file()
                    and filecmp.cmp(item, destination, shallow=False)
                ):
                    item.unlink()
                else:
                    self._preserve_conflict(item, conflict)
            else:
                move_path_safely(item, destination)

    def _link(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            if source.resolve() == target.resolve():
                return
            conflicts = target.parent / ".autodl-migration-conflicts" / target.name
            self._preserve_conflict(source, conflicts / source.name)
        elif source.is_dir():
            conflicts = target.parent / ".autodl-migration-conflicts" / target.name
            self._merge_directory(source, target, conflicts)
            source.rmdir()
        elif source.exists():
            conflicts = target.parent / ".autodl-migration-conflicts" / target.name
            self._preserve_conflict(source, conflicts / source.name)
        target.mkdir(parents=True, exist_ok=True)
        source.symlink_to(target)

    @hookimpl
    def setup(self, context: AppContext) -> None:
        comfy_dir = context.artifacts.comfy_dir or context.comfy_dir
        data_dir = context.workspace_data_dir or (context.base_dir / "comfyui-workspace")
        output_dir = context.output_dir or (data_dir / "output")
        require_managed_storage_mount(data_dir, output_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.get_manifest(context)
        workspace_dirs = cast(List[str], manifest.get("workspace_dirs", ["user", "output"]))
        for name in workspace_dirs:
            target = output_dir if name == "output" else data_dir / name
            self._link(comfy_dir / name, target)
        context.artifacts.workspace_data_dir = data_dir
        context.artifacts.output_dir = output_dir
        logger.info("  -> 本地 workspace 已就绪: %s", data_dir)

    @hookimpl
    def start(self, context: AppContext) -> None:
        return None

    @hookimpl
    def stop(self, context: AppContext) -> None:
        return None
