"""
AutoDL 自动化装配入口
"""
import argparse
import logging
import sys
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.addons.comfy_core.plugin import ComfyAddon
from src.addons.system.plugin import SystemAddon
from src.core.adapters import FileStateManager, SubprocessRunner
from src.core.artifacts import Artifacts
from src.core.interface import AppContext, BaseAddon
from src.core.results import PipelineResult, PluginResult
from src.core.runtime import (
    DEFAULT_BASE_DIR,
    DEFAULT_COMFY_DIR,
    configure_cache_environment,
    require_managed_storage_mount,
    resolve_runtime_config,
)
from src.core.utils import logger, setup_logger
from src.lib.network import stop_proxy

# ============================================================
# 全局常量
# ============================================================
BASE_DIR = DEFAULT_BASE_DIR
COMFY_DIR = DEFAULT_COMFY_DIR  # ComfyUI 安装目录（系统盘）
DEFAULT_PORT = 6006


def create_pipeline() -> List[BaseAddon]:
    """Installation only; data layout belongs to init/migrate."""
    return [SystemAddon(), ComfyAddon()]


def _load_manifests_from_package() -> Dict[str, Dict[str, Any]]:
    """Load bundled manifest.yaml files when installed as a package."""
    manifests: Dict[str, Dict[str, Any]] = {}
    for package_name in ("src.addons", "src.lib"):
        try:
            package_root = resources.files(package_name)
        except ModuleNotFoundError:
            continue

        for module in package_root.iterdir():
            if not module.is_dir():
                continue
            manifest = module / "manifest.yaml"
            if manifest.is_file():
                with manifest.open("r", encoding="utf-8") as f:
                    manifests[module.name] = yaml.safe_load(f) or {}
    return manifests


def load_manifests(code_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    预加载所有模块的 manifest.yaml，统一作为配置来源。
    
    扫描目录:
        1. src/addons/*/manifest.yaml  - 插件配置
        2. src/lib/*/manifest.yaml     - 库配置
    
    返回字典 key 为模块目录名，如 "comfy_core"、"download"。
    """
    config_logger = logging.getLogger("autodl_setup")
    manifests: Dict[str, Dict[str, Any]] = {}
    
    scan_dirs = [
        code_root / "src" / "addons",
        code_root / "src" / "lib",
    ]
    
    for parent_dir in scan_dirs:
        if not parent_dir.exists():
            continue
        for module_dir in parent_dir.iterdir():
            if not module_dir.is_dir():
                continue
            manifest_file = module_dir / "manifest.yaml"
            if manifest_file.exists():
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifests[module_dir.name] = yaml.safe_load(f) or {}
                config_logger.debug(f"  -> [Manifest] 已加载: {manifest_file.relative_to(code_root)}")

    return manifests or _load_manifests_from_package()


def create_context(debug: bool = False, load_artifacts: bool = False) -> AppContext:
    """
    创建应用上下文
    
    Args:
        debug: 调试模式
        load_artifacts: 是否从持久化文件加载 artifacts（用于 start/stop 阶段）
    """
    code_root = Path(__file__).resolve().parent.parent
    runtime = resolve_runtime_config(code_root)
    require_managed_storage_mount(
        runtime.base_dir,
        runtime.workspace_dir,
        runtime.workspace_data_dir,
        runtime.models_dir,
        runtime.output_dir,
        runtime.downloads_dir,
        runtime.cache_dir,
        runtime.temp_dir,
    )
    configure_cache_environment(runtime)
    runtime.workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # 根据场景决定是否加载已持久化的 artifacts
    if load_artifacts:
        artifacts = Artifacts.load(runtime.workspace_dir)
    else:
        artifacts = Artifacts()
    
    context = AppContext(
        project_root=runtime.code_root,
        code_root=runtime.code_root,
        base_dir=runtime.base_dir,
        workspace_dir=runtime.workspace_dir,
        workspace_data_dir=runtime.workspace_data_dir,
        models_dir=runtime.models_dir,
        output_dir=runtime.output_dir,
        downloads_dir=runtime.downloads_dir,
        cache_dir=runtime.cache_dir,
        temp_dir=runtime.temp_dir,
        comfy_dir=runtime.comfy_dir,
        config_file=runtime.config_file,
        python_env_dir=runtime.python_env_dir,
        local_config=runtime.local_config,
        cmd=SubprocessRunner(),
        state=FileStateManager(runtime.workspace_dir),
        artifacts=artifacts,
        debug=debug,
        addon_manifests=load_manifests(runtime.code_root),
    )
    return context


def execute(
    action: str, 
    context: AppContext, 
) -> PipelineResult:
    """
    执行插件 Pipeline
    
    Args:
        action: 生命周期动作 (setup/start/stop)
        context: 应用上下文
    """
    pipeline = create_pipeline()
    result = PipelineResult(action=action)
    
    # 正常顺序执行
    logger.info(f"\n>>> 开始执行 Pipeline: [{action.upper()}]")
    
    for addon in pipeline:
        logger.info(f"  -> {addon.name}")
        method = getattr(addon, action, None)
        if method:
            try:
                plugin_result = method(context)
                if action == "stop" and isinstance(plugin_result, PluginResult):
                    result.add_plugin_result(addon.name, plugin_result)
            except Exception as e:
                if action == "stop":
                    logger.error(f"  -> [{addon.name}] stop 失败: {e}")
                    result.add_failure(addon.name, str(e))
                    continue
                raise
        
    
    # setup 完成后持久化 artifacts，供后续 start/stop 使用
    if action == "setup":
        try:
            artifacts_dir = context.workspace_dir or context.project_root
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            context.artifacts.save(artifacts_dir)
            logger.info("  -> Artifacts 已持久化")
        except Exception as e:
            raise RuntimeError("Artifacts 持久化失败") from e

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL 自动化装配调度器")
    parser.add_argument("action", choices=["setup", "start", "stop"], help="生命周期动作")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--vram-mode", choices=["high", "normal"])
    args = parser.parse_args()
    if args.vram_mode and args.action != "start":
        parser.error("--vram-mode 仅用于 start")

    # 初始化日志（必须在所有其他操作之前）
    runtime = resolve_runtime_config(Path(__file__).resolve().parent.parent)
    require_managed_storage_mount(runtime.workspace_dir)
    runtime.workspace_dir.mkdir(parents=True, exist_ok=True)
    log_file = runtime.workspace_dir / "autodl-setup.log"
    setup_logger(log_file, debug=args.debug)

    context = create_context(debug=args.debug, load_artifacts=args.action in ("start", "stop"))
    if args.action == "start":
        context.vram_mode = args.vram_mode

    # 创建上下文并执行
    # start/stop 需要加载 setup 阶段持久化的 artifacts

    result = execute(args.action, context)
    if args.action == "stop":
        stop_proxy()
    if args.action == "stop" and not result.ok:
        logger.error("\n>>> 停止失败：")
        for issue in result.failures:
            logger.error(f"  -> [{issue.plugin}] {issue.message}")
            if issue.next_step:
                logger.error(f"     下一步: {issue.next_step}")
        sys.exit(1)


if __name__ == "__main__":
    main()
