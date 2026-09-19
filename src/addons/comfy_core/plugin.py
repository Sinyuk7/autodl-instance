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
        """Only trust a completed setup whose ComfyUI entrypoint still exists."""
        main_py = self._get_comfy_dir(ctx) / "main.py"
        if ctx.state.is_completed(StateKey.COMFY_INSTALLED) and main_py.exists():
            return True

        if ctx.state.is_completed(StateKey.COMFY_INSTALLED):
            ctx.state.clear(StateKey.COMFY_INSTALLED)
        return False

    def _get_pypi_mirror(self, ctx: AppContext) -> str:
        """Return the complete PyPI index required by current ComfyUI releases."""
        manifest = self.get_manifest(ctx)
        return manifest.get("pypi_index_url") or "https://pypi.org/simple"

    def _install_comfy_cli(self, ctx: AppContext) -> None:
        """安装 comfy-cli（依赖 SystemAddon 产出的 uv_bin）"""
        uv_bin = ctx.artifacts.uv_bin
        if not uv_bin or not uv_bin.exists():
            raise RuntimeError("uv 未安装，请确保 SystemAddon 在 ComfyAddon 之前执行")

        manifest = self.get_manifest(ctx)
        comfy_cli_version = str(manifest.get("comfy_cli_version") or "1.20.0")
        pypi_mirror = self._get_pypi_mirror(ctx)

        cmd = [
            str(uv_bin),
            "pip",
            "install",
            "--system",
            "--upgrade",
            f"comfy-cli=={comfy_cli_version}",
            "--index-url",
            pypi_mirror,
        ]
        if ctx.debug:
            cmd.insert(3, "--verbose")

        logger.info(f"  -> 正在确认 comfy-cli {comfy_cli_version}...")
        ctx.cmd.run(cmd, check=True)
        logger.info("  -> comfy-cli 引擎就绪。")

    def _build_install_command(self, ctx: AppContext, comfy_dir: Path) -> list[str]:
        manifest = self.get_manifest(ctx)
        torch_manifest = ctx.addon_manifests.get("torch_engine", {})
        index_url = self._get_pypi_mirror(ctx)
        comfyui_version = str(manifest.get("comfyui_version") or "latest")
        cuda_version = str(torch_manifest.get("min_cuda_version") or "13.0")

        cmd = [
            "env",
            f"PIP_INDEX_URL={index_url}",
            f"UV_DEFAULT_INDEX={index_url}",
            "comfy",
            "--workspace",
            str(comfy_dir),
            "--skip-prompt",
            "install",
            "--version",
            comfyui_version,
            "--nvidia",
            "--cuda-version",
            cuda_version,
            "--skip-torch-or-directml",
        ]
        if manifest.get("fast_deps", True):
            cmd.append("--fast-deps")
        if (comfy_dir / "main.py").exists():
            cmd.append("--restore")
        return cmd

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
            # Explicit flags keep setup non-interactive and reuse TorchAddon.
            logger.info(f"  -> 正在部署至 {comfy_dir}...")
            ctx.cmd.run(
                self._build_install_command(ctx, comfy_dir),
                check=True,
                capture_output=False,
            )
            ctx.state.mark_completed(StateKey.COMFY_INSTALLED)
            logger.info("  -> ComfyUI 核心引擎装配完成！")
            self.log(ctx, "setup", "installed")
        
        # 产出：供后续插件使用
        ctx.artifacts.comfy_dir = comfy_dir
        ctx.artifacts.custom_nodes_dir = comfy_dir / "custom_nodes"
        ctx.artifacts.user_dir = comfy_dir / "user"
        workspace_data_dir = ctx.workspace_data_dir or (ctx.base_dir / "comfyui-workspace")
        ctx.artifacts.output_dir = workspace_data_dir / "output"

    @hookimpl
    def start(self, context: AppContext) -> None:
        logger.info("\n>>> [Comfy Core] 正在启动 ComfyUI 服务...")
        ctx = context
        
        comfy_dir = ctx.artifacts.comfy_dir or self._get_comfy_dir(ctx)
        port = self.DEFAULT_PORT

        try:
            from src.status import collect_quick_checks

            checks = collect_quick_checks(
                project_root=ctx.project_root,
                base_dir=ctx.base_dir,
                workspace_dir=ctx.workspace_dir,
                workspace_data_dir=ctx.workspace_data_dir,
                comfy_dir=comfy_dir,
            )
            problems = [check for check in checks if check.is_problem]
            if problems:
                logger.warning("  -> [WARN] 启动前状态检查发现问题，但不会阻塞启动：")
                for check in problems:
                    logger.warning(f"     [{check.status}] {check.name}: {check.detail}")
        except Exception as e:
            logger.warning(f"  -> [WARN] 启动前状态检查失败，继续启动: {e}")
        
        release_port(port)
        
        logger.info(f"  -> ComfyUI 目录: {comfy_dir}")
        logger.info(f"  -> 监听端口: {port}")
        
        try:
            ctx.cmd.run([
                "comfy", "--workspace", str(comfy_dir), "launch",
                "--", "--port", str(port), "--listen", "0.0.0.0"
            ], check=True, capture_output=False)
        except KeyboardInterrupt:
            logger.info("\n  -> 服务已安全关闭。")

    @hookimpl
    @hookimpl
    def stop(self, context: AppContext) -> None:
        release_port(self.DEFAULT_PORT)
