"""
Userdata Addon - ComfyUI 用户数据管理
负责将 user/ 和 script_examples/ 等目录替换为指向数据目录的软链接
"""
import shutil
from pathlib import Path
from typing import  List, cast

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.results import PluginResult
from src.core.runtime import write_data_repo_metadata
from src.core.utils import logger

from .strategy import GitRepoStrategy, LocalStrategy, SyncStrategy


class UserdataAddon(BaseAddon):
    """ComfyUI 用户数据管理插件"""

    module_dir = "userdata"
    DATA_DIR_NAME = "my-comfyui-backup"
    EXAMPLE_DIR_NAME = f"{DATA_DIR_NAME}.example"

    def _get_strategy(self, ctx: AppContext) -> SyncStrategy:
        """根据配置选择同步策略"""
        repo_url = ctx.local_config.get("userdata_repo") or ""
        
        if repo_url.strip():
            return GitRepoStrategy(repo_url.strip(), (ctx.userdata_dir or Path(self.DATA_DIR_NAME)).name, ctx.cmd)
        return LocalStrategy((ctx.code_root or ctx.project_root) / self.EXAMPLE_DIR_NAME)

    def _get_data_dir(self, ctx: AppContext) -> Path:
        """获取 RFC-007 用户数据仓库目录。"""
        return ctx.userdata_dir or (ctx.base_dir / self.DATA_DIR_NAME)

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

        data_dir = self._get_data_dir(ctx)
        strategy = self._get_strategy(ctx)
        manifest = self.get_manifest(ctx)
        sync_dirs = cast(List[str], manifest.get("sync_dirs", []))
        
        # 准备数据目录
        if not strategy.prepare(data_dir, ctx):
            logger.error("  -> 数据目录准备失败")
            return

        data_repo_config = {
            "sync_dirs": sync_dirs,
            "models_dir": str(ctx.models_dir),
            "workspace_dir": str(ctx.workspace_dir),
        }
        if ctx.local_config.get("userdata_repo"):
            data_repo_config["userdata_repo"] = ctx.local_config["userdata_repo"]
        write_data_repo_metadata(data_dir, config=data_repo_config)
        ctx.artifacts.userdata_dir = data_dir

        # 建立软链接
        comfy_dir = ctx.artifacts.comfy_dir
        if not sync_dirs or not comfy_dir or not comfy_dir.exists():
            return

        for dir_name in sync_dirs:
            self._setup_symlink(comfy_dir / dir_name, data_dir / dir_name)
        
        logger.info("  -> 用户数据就绪")

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> PluginResult:
        """同步：推送数据变更"""
        logger.info("\n>>> [Userdata] 同步用户数据...")
        ctx = context
        
        data_dir = self._get_data_dir(ctx)
        if not data_dir.exists():
            return PluginResult.failure(
                f"用户数据目录不存在: {data_dir}",
                "请先运行 autodl config set userdata-repo <git-url> 或 autodl setup",
            )
        
        strategy = self._get_strategy(ctx)
        return strategy.push(data_dir, ctx)
