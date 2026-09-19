"""Keep ComfyUI working data on the AutoDL data disk.

This is deliberately local-only: no remote repository or upload workflow is
involved.
"""
import shutil
from pathlib import Path
from typing import List, cast

from src.core.interface import AppContext, BaseAddon, hookimpl
from src.core.utils import logger


class WorkspaceAddon(BaseAddon):
    module_dir = "workspace"

    def _link(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            if source.resolve() == target.resolve():
                return
            source.unlink()
        elif source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                destination = target / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif not destination.exists():
                    shutil.copy2(item, destination)
            shutil.rmtree(source)
        elif source.exists():
            source.unlink()
        target.mkdir(parents=True, exist_ok=True)
        source.symlink_to(target)

    @hookimpl
    def setup(self, context: AppContext) -> None:
        comfy_dir = context.artifacts.comfy_dir or context.comfy_dir
        data_dir = context.workspace_data_dir or (context.base_dir / "comfyui-workspace")
        data_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.get_manifest(context)
        workspace_dirs = cast(List[str], manifest.get("workspace_dirs", ["user", "output"]))
        for name in workspace_dirs:
            self._link(comfy_dir / name, data_dir / name)
        context.artifacts.workspace_data_dir = data_dir
        logger.info("  -> 本地 workspace 已就绪: %s", data_dir)

    @hookimpl
    def start(self, context: AppContext) -> None:
        return None

    @hookimpl
    def stop(self, context: AppContext) -> None:
        return None
