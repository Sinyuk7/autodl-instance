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
        """从 context 获取 ComfyUI 安装目录"""
        return ctx.comfy_dir

    def _get_output_target_dir(self, ctx: AppContext) -> Path:
        """output 目录在 tmp 盘的实际存储位置"""
        return ctx.base_dir / "ComfyUI_output"

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

    def _setup_output_symlink(self, ctx: AppContext, comfy_dir: Path) -> None:
        """将 output 目录软链接到 tmp 盘
        
        目的：产出文件（图片/视频）可能很大，放在持久化的 tmp 盘
        
        注意：Windows 创建软链接需要管理员权限，测试环境下会跳过
        """
        import platform
        
        output_link = comfy_dir / "output"
        target_dir = self._get_output_target_dir(ctx)
        
        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 幂等检查：已是正确软链接则跳过
        if output_link.is_symlink():
            if output_link.resolve() == target_dir.resolve():
                logger.info(f"  -> output 软链接已就绪 → {target_dir}")
                return
            else:
                # 软链接指向错误位置，删除重建
                output_link.unlink()
        
        # 如果 output 是真实目录，先迁移内容再删除
        if output_link.exists() and output_link.is_dir():
            logger.info(f"  -> 迁移 output 内容到 {target_dir}...")
            for item in output_link.iterdir():
                dest = target_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            shutil.rmtree(output_link)
        
        # 创建软链接（Windows 需要管理员权限，测试环境跳过）
        try:
            output_link.symlink_to(target_dir)
            logger.info(f"  -> output 软链接已创建 → {target_dir}")
        except OSError as e:
            if platform.system() == "Windows":
                logger.warning(f"  -> [SKIP] Windows 无法创建软链接（需管理员权限）: {e}")
                # 确保 output 目录存在，作为 fallback
                output_link.mkdir(parents=True, exist_ok=True)
            else:
                raise

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
        
        # 设置 output 软链接（指向 tmp 盘）
        self._setup_output_symlink(ctx, comfy_dir)
        
        # 产出：供后续插件使用
        ctx.artifacts.comfy_dir = comfy_dir
        ctx.artifacts.custom_nodes_dir = comfy_dir / "custom_nodes"
        ctx.artifacts.user_dir = comfy_dir / "user"
        ctx.artifacts.output_dir = self._get_output_target_dir(ctx)

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