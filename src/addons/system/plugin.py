"""
System Addon - 基础设施装配
负责工具和 ComfyUI 独立环境
"""
import os
import shutil
from pathlib import Path

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.utils import logger


class SystemAddon(BaseAddon):
    module_dir = "system"

    @hookimpl
    def setup(self, context: AppContext) -> None:
        """执行环境初始化钩子"""
        logger.info("\n>>> [System] 开始执行基础设施装配...")
        ctx = context
        
        self._install_system_tools(ctx)
        self._install_uv(ctx)
        from src.core.python_env import ensure_python_env
        ensure_python_env(ctx)

    def _install_system_tools(self, ctx: AppContext) -> None:
        """任务 0: 安装必要的系统工具 (lsof, fuser 等)"""
        if shutil.which("lsof") and shutil.which("fuser"):
            return
        
        logger.info("  -> 正在安装系统工具 (lsof, psmisc)...")
        try:
            ctx.cmd.run(["apt-get", "update"], timeout=60, check=False)
            ctx.cmd.run(
                ["apt-get", "install", "-y", "lsof", "psmisc"],
                timeout=60, check=False
            )
            logger.info("  -> 系统工具安装完成。")
        except Exception as e:
            logger.warning(f"  -> [WARN] 系统工具安装失败: {e}，端口清理功能可能受限")

    def _install_uv(self, ctx: AppContext) -> None:
        """任务 2: 安装 uv 包管理器"""
        uv_path = Path.home() / ".local" / "bin"
        uv_bin = uv_path / "uv"
        available = shutil.which("uv")
        if not uv_bin.exists() and available:
            uv_bin = Path(available)
        
        if not uv_bin.exists():
            logger.info("  -> 未检测到 uv，正在执行静默安装...")
            ctx.cmd.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True, check=True,
            )
            logger.info("  -> uv 安装完成。")
        else:
            logger.info("  -> uv 已就绪。")
        
        if str(uv_path) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{uv_path}:{os.environ.get('PATH', '')}"
        
        # 产出：供后续插件使用
        ctx.artifacts.uv_bin = uv_bin

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def stop(self, context: AppContext) -> None:
        pass
