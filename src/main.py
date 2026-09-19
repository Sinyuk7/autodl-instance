"""
AutoDL 自动化装配入口
"""
import argparse
import logging
import os
import sys
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.interface import AppContext, BaseAddon
from src.core.adapters import SubprocessRunner, FileStateManager
from src.core.artifacts import Artifacts
from src.core.results import PipelineResult, PluginResult
from src.core.runtime import (
    DEFAULT_BASE_DIR,
    DEFAULT_COMFY_DIR,
    resolve_runtime_config,
)
from src.core.utils import setup_logger, logger, kill_process_by_name
from src.lib.network import setup_network, invalidate_network_cache, stop_proxy

# 插件导入
from src.addons.system.plugin import SystemAddon
from src.addons.torch_engine.plugin import TorchAddon
from src.addons.comfy_core.plugin import ComfyAddon
from src.addons.workspace.plugin import WorkspaceAddon
from src.addons.nodes.plugin import NodesAddon
from src.addons.models.plugin import ModelAddon


# ============================================================
# 全局常量
# ============================================================
BASE_DIR = DEFAULT_BASE_DIR
COMFY_DIR = DEFAULT_COMFY_DIR  # ComfyUI 安装目录（系统盘）
DEFAULT_PORT = 6006


def create_pipeline() -> List[BaseAddon]:
    """
    定义插件执行顺序（硬编码，显式声明）
    
    顺序说明：
    1. system       - 基础设施（uv, comfy-cli, 缓存迁移）
    2. torch_engine - PyTorch CUDA 环境
    3. comfy_core   - ComfyUI 核心安装 → 产出 comfy_dir
    4. workspace    - 本地工作数据持久化 → 依赖 comfy_dir
    5. nodes        - 节点管理 → 依赖 comfy_dir
    6. models       - 模型管理 → 依赖 comfy_dir
    
    注意: 代理服务（turbo / mihomo）在 setup_network() 中已初始化，
    不作为 pipeline 插件，因为所有插件都依赖网络。
    """
    return [
        SystemAddon(),
        TorchAddon(),
        ComfyAddon(),
        WorkspaceAddon(),
        NodesAddon(),
        ModelAddon(),
    ]


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
    
    返回字典 key 为模块目录名，如 "torch_engine"、"download"。
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
        comfy_dir=runtime.comfy_dir,
        config_file=runtime.config_file,
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
    until: Optional[str] = None,
    only: Optional[str] = None,
) -> PipelineResult:
    """
    执行插件 Pipeline
    
    Args:
        action: 生命周期动作 (setup/start/stop)
        context: 应用上下文
        until: 执行到指定插件为止（包含）
        only: 只执行指定插件（跳过依赖，危险模式）
    """
    pipeline = create_pipeline()
    result = PipelineResult(action=action)
    
    # --only: 只执行单个插件
    if only:
        addon = next((a for a in pipeline if a.name == only), None)
        if not addon:
            logger.error(f"未知插件: {only}")
            sys.exit(1)
        
        logger.info(f"\n>>> 单独执行: {addon.name}.{action}()")
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
                    return result
                raise
        return result
    
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
        
        # --until: 执行到指定插件停止
        if until and addon.name == until:
            logger.info(f"  -> 已到达目标插件 [{until}]，停止")
            break
    
    # setup 完成后持久化 artifacts，供后续 start/stop 使用
    if action == "setup":
        try:
            artifacts_dir = context.workspace_dir or context.project_root
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            context.artifacts.save(artifacts_dir)
            logger.info("  -> Artifacts 已持久化")
        except Exception as e:
            logger.error(f"  -> Artifacts 持久化失败: {e}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL 自动化装配调度器")
    parser.add_argument("action", choices=["setup", "start", "stop"], help="生命周期动作")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--until", type=str, help="执行到指定插件为止")
    parser.add_argument("--only", type=str, help="只执行指定插件（危险模式）")
    args = parser.parse_args()

    # 初始化日志（必须在所有其他操作之前）
    runtime = resolve_runtime_config(Path(__file__).resolve().parent.parent)
    runtime.workspace_dir.mkdir(parents=True, exist_ok=True)
    log_file = runtime.workspace_dir / "autodl-setup.log"
    setup_logger(log_file, debug=args.debug)

    # 清理残留进程
    kill_process_by_name("python.*src.main", exclude_pid=os.getpid())

    # setup 动作时清除网络状态缓存，确保走完整初始化流程
    # 其他动作以及独立 CLI（model download）则复用缓存
    if args.action == "setup":
        invalidate_network_cache()

    # 初始化网络环境 (代理 + 镜像 + Token)
    setup_network()

    # 创建上下文并执行
    # start/stop 需要加载 setup 阶段持久化的 artifacts
    load_artifacts = args.action in ("start", "stop")
    context = create_context(debug=args.debug, load_artifacts=load_artifacts)

    result = execute(args.action, context, until=args.until, only=args.only)
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
