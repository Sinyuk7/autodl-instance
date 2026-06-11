"""
System Addon - 基础设施装配
负责 uv 安装、bin 脚本生成
"""
import os
import shutil
from pathlib import Path
from textwrap import dedent

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
        self._generate_bin_scripts(ctx)

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

    def _generate_bin_scripts(self, ctx: AppContext) -> None:
        """任务 3: 生成 bin/ 全局命令脚本并配置 PATH"""
        workspace_dir = ctx.workspace_dir or (ctx.base_dir / "autodl-workspace")
        bin_dir = workspace_dir / "bin"
        
        bin_dir.mkdir(parents=True, exist_ok=True)

        def command_script(command: str, description: str) -> str:
            return dedent(f"""\
                #!/bin/bash
                # {description} - 自动生成，请勿手动修改
                if ! command -v autodl >/dev/null 2>&1; then
                  echo "autodl command not found. Install it with: uv tool install autodl-instance" >&2
                  exit 127
                fi
                exec autodl {command} "$@"
            """)

        turbo_script = dedent("""\
            #!/bin/bash
            # AutoDL 网络环境初始化 - 自动生成，请勿手动修改
            # 用法: source turbo
            if ! command -v autodl >/dev/null 2>&1; then
              echo "autodl command not found. Install it with: uv tool install autodl-instance" >&2
              return 127 2>/dev/null || exit 127
            fi
            eval "$(autodl turbo)"
        """)
        
        scripts = {
            "turbo": turbo_script,
            "bye": command_script("bye", "AutoDL 离线同步命令"),
            "model": command_script("model", "ComfyUI 模型管理命令"),
            "status": command_script("status", "AutoDL 工作区状态检查"),
            "doctor": command_script("doctor", "AutoDL 工作区深度诊断"),
            "start": command_script("start", "ComfyUI 启动命令"),
        }
        
        for script_name, content in scripts.items():
            script_path = bin_dir / script_name
            script_path.write_text(content)
            script_path.chmod(0o755)
            logger.info(f"  -> 已生成命令脚本: {script_path}")
        
        bashrc_path = Path.home() / ".bashrc"
        path_export = f'export PATH="{bin_dir}:$PATH"'
        
        if bashrc_path.exists():
            bashrc_content = bashrc_path.read_text()
            if str(bin_dir) not in bashrc_content:
                with bashrc_path.open("a") as f:
                    f.write(f"\n# AutoDL Instance 全局命令\n{path_export}\n")
                logger.info(f"  -> 已将 bin/ 目录加入 PATH")
            else:
                logger.info(f"  -> PATH 配置已存在，跳过。")
        
        os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
        
        # 产出
        ctx.artifacts.bin_dir = bin_dir

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        pass
