"""
ComfyUI 核心安装插件
"""
import shutil
from pathlib import Path

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.schema import StateKey
from src.core.utils import logger, release_port


class ComfyAddon(BaseAddon):
    module_dir = "comfy_core"
    DEFAULT_PORT = 6006

    def _get_comfy_dir(self, ctx: AppContext) -> Path:
        return ctx.base_dir / "ComfyUI"

    def _is_installed(self, ctx: AppContext) -> bool:
        """检查是否已安装"""
        if ctx.state.is_completed(StateKey.COMFY_INSTALLED):
            return True
        
        # 目录存在也算已安装
        main_py = self._get_comfy_dir(ctx) / "main.py"
        if main_py.exists():
            ctx.state.mark_completed(StateKey.COMFY_INSTALLED)
            return True
        
        return False

    def _get_pypi_mirror(self, ctx: AppContext) -> str:
        """从 manifest 获取 PyPI 镜像源"""
        manifest = self.get_manifest(ctx)
        return manifest.get("pypi_mirror") or ""

    def _install_comfy_cli(self, ctx: AppContext) -> None:
        """安装 comfy-cli（依赖 SystemAddon 产出的 uv_bin）"""
        if shutil.which("comfy"):
            logger.info("  -> comfy-cli 已就绪，跳过安装。")
            return
        
        uv_bin = ctx.artifacts.uv_bin
        if not uv_bin or not uv_bin.exists():
            raise RuntimeError("uv 未安装，请确保 SystemAddon 在 ComfyAddon 之前执行")
        
        pypi_mirror = self._get_pypi_mirror(ctx)
        
        cmd = [str(uv_bin), "pip", "install", "--system", "comfy-cli"]
        if ctx.debug:
            cmd.insert(3, "--verbose")
        if pypi_mirror:
            cmd.extend(["-i", pypi_mirror])
            logger.info(f"  -> 正在通过 uv 安装 comfy-cli (镜像: {pypi_mirror})...")
        else:
            logger.info("  -> 正在通过 uv 安装 comfy-cli...")
        
        ctx.cmd.run(cmd, check=True)
        logger.info("  -> comfy-cli 引擎就绪。")

    @hookimpl
    def setup(self, context: AppContext) -> None:
        logger.info("\n>>> [Comfy Core] 开始装配 ComfyUI 引擎...")
        ctx = context
        
        # 确保 comfy-cli 可用
        self._install_comfy_cli(ctx)
        
        comfy_dir = self._get_comfy_dir(ctx)
        
        # 幂等检查
        if self._is_installed(ctx):
            logger.info("  -> [SKIP] ComfyUI 已安装")
            self.log(ctx, "setup", "skipped:already_installed")
        else:
            # 执行安装
            logger.info(f"  -> 正在部署至 {comfy_dir}...")
            ctx.cmd.run(
                ["comfy", "--workspace", str(comfy_dir), "install"],
                check=True,
            )
            ctx.state.mark_completed(StateKey.COMFY_INSTALLED)
            logger.info("  -> ComfyUI 核心引擎装配完成！")
            self.log(ctx, "setup", "installed")
        
        # 产出：供后续插件使用
        ctx.artifacts.comfy_dir = comfy_dir
        ctx.artifacts.custom_nodes_dir = comfy_dir / "custom_nodes"
        ctx.artifacts.user_dir = comfy_dir / "user"

    @hookimpl
    def start(self, context: AppContext) -> None:
        logger.info("\n>>> [Comfy Core] 正在启动 ComfyUI 服务...")
        ctx = context
        
        comfy_dir = ctx.artifacts.comfy_dir or self._get_comfy_dir(ctx)
        port = self.DEFAULT_PORT
        
        release_port(port)
        
        logger.info(f"  -> ComfyUI 目录: {comfy_dir}")
        logger.info(f"  -> 监听端口: {port}")
        
        try:
            ctx.cmd.run([
                "comfy", "--workspace", str(comfy_dir), "launch",
                "--", "--port", str(port), "--listen", "127.0.0.1"
            ], check=True, capture_output=False)
        except KeyboardInterrupt:
            logger.info("\n  -> 服务已安全关闭。")

    @hookimpl
    def sync(self, context: AppContext) -> None:
        pass