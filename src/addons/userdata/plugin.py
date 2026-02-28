"""
Userdata Addon - ComfyUI 用户数据管理
负责将 user/ 和 script_examples/ 等目录替换为指向数据目录的软链接
"""
import shutil
from pathlib import Path
from typing import  List, cast

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.utils import logger

from .strategy import GitRepoStrategy, LocalStrategy, SyncStrategy


class UserdataAddon(BaseAddon):
    """ComfyUI 用户数据管理插件"""

    module_dir = "userdata"
    DATA_DIR_NAME = "my-comfyui-backup"
    EXAMPLE_DIR_NAME = f"{DATA_DIR_NAME}.example"

    def _get_strategy(self, ctx: AppContext) -> SyncStrategy:
        """根据配置选择同步策略"""
        manifest = self.get_manifest(ctx)
        repo_url = manifest.get("userdata_repo") or ""
        
        if repo_url.strip():
            return GitRepoStrategy(repo_url.strip(), self.DATA_DIR_NAME, ctx.cmd)
        return LocalStrategy(ctx.project_root / self.EXAMPLE_DIR_NAME)

    def _setup_symlink(self, comfy_path: Path, data_path: Path) -> None:
        """建立软链接: comfy_path → data_path"""
        name = comfy_path.name
        
        # 已是正确软链接
        if comfy_path.is_symlink():
            if comfy_path.resolve() == data_path.resolve():
                return
            comfy_path.unlink()
        
        # 物理目录 → 迁移内容后删除
        elif comfy_path.is_dir():
            data_path.mkdir(parents=True, exist_ok=True)
            for item in comfy_path.iterdir():
                dest = data_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                elif not dest.exists():
                    shutil.copy2(item, dest)
            shutil.rmtree(comfy_path)
            logger.debug(f"  -> 迁移 {name} 到数据目录")
        
        # 确保目标存在
        data_path.mkdir(parents=True, exist_ok=True)
        try:
            comfy_path.symlink_to(data_path)
            logger.debug(f"  -> 链接 {name}")
        except OSError as e:
            # Windows 需要管理员权限创建软链接
            logger.warning(f"  -> [SKIP] Windows 无法创建软链接（需管理员权限）: {e}")

    @hookimpl
    def setup(self, context: AppContext) -> None:
        """初始化：准备数据目录 + 建立软链接"""
        logger.info("\n>>> [Userdata] 初始化用户数据...")
        ctx = context

        data_dir = ctx.project_root / self.DATA_DIR_NAME
        strategy = self._get_strategy(ctx)
        
        # 准备数据目录
        if not strategy.prepare(data_dir, ctx):
            logger.error("  -> 数据目录准备失败")
            return

        # 建立软链接
        manifest = self.get_manifest(ctx)
        sync_dirs = cast(List[str], manifest.get("sync_dirs", []))
        
        comfy_dir = ctx.artifacts.comfy_dir
        if not sync_dirs or not comfy_dir or not comfy_dir.exists():
            return

        for dir_name in sync_dirs:
            self._setup_symlink(comfy_dir / dir_name, data_dir / dir_name)
        
        # 产出
        ctx.artifacts.userdata_dir = data_dir
        logger.info("  -> 用户数据就绪")

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        """同步：推送数据变更"""
        logger.info("\n>>> [Userdata] 同步用户数据...")
        ctx = context
        
        data_dir = ctx.project_root / self.DATA_DIR_NAME
        if not data_dir.exists():
            return
        
        strategy = self._get_strategy(ctx)
        strategy.push(data_dir, ctx)