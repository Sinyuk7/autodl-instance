"""
AutoDL 自动化装配入口
"""
import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.interface import AppContext, BaseAddon
from src.core.adapters import SubprocessRunner, FileStateManager
from src.core.artifacts import Artifacts
from src.core.utils import setup_logger, logger, kill_process_by_name
from src.lib.network import setup_network, sync_proxy_config

# 插件导入
from src.addons.system.plugin import SystemAddon
from src.addons.git_config.plugin import GitAddon
from src.addons.torch_engine.plugin import TorchAddon
from src.addons.comfy_core.plugin import ComfyAddon
from src.addons.userdata.plugin import UserdataAddon
from src.addons.nodes.plugin import NodesAddon
from src.addons.models.plugin import ModelAddon


# ============================================================
# 全局常量
# ============================================================
BASE_DIR = Path("/root/autodl-tmp")
COMFY_DIR = Path("/root/ComfyUI")  # ComfyUI 安装目录（系统盘）
DEFAULT_PORT = 6006


def create_pipeline() -> List[BaseAddon]:
    """
    定义插件执行顺序（硬编码，显式声明）
    
    顺序说明：
    1. system       - 基础设施（uv, comfy-cli, 缓存迁移）
    2. git_config   - Git/SSH 配置
    3. torch_engine - PyTorch CUDA 环境
    4. comfy_core   - ComfyUI 核心安装 → 产出 comfy_dir
    5. userdata     - 用户数据软链接 → 依赖 comfy_dir
    6. nodes        - 节点管理 → 依赖 comfy_dir, user_dir
    7. models       - 模型管理 → 依赖 comfy_dir
    
    注意: 代理服务（turbo / mihomo）在 setup_network() 中已初始化，
    不作为 pipeline 插件，因为所有插件都依赖网络。
    """
    return [
        SystemAddon(),
        GitAddon(),
        TorchAddon(),
        ComfyAddon(),
        UserdataAddon(),
        NodesAddon(),
        ModelAddon(),
    ]


def load_manifests(project_root: Path) -> Dict[str, Dict[str, Any]]:
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
        project_root / "src" / "addons",
        project_root / "src" / "lib",
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
                config_logger.debug(f"  -> [Manifest] 已加载: {manifest_file.relative_to(project_root)}")
    
    return manifests


def create_context(debug: bool = False, load_artifacts: bool = False) -> AppContext:
    """
    创建应用上下文
    
    Args:
        debug: 调试模式
        load_artifacts: 是否从持久化文件加载 artifacts（用于 start/sync 阶段）
    """
    project_root = Path(__file__).resolve().parent.parent
    
    # 根据场景决定是否加载已持久化的 artifacts
    if load_artifacts:
        artifacts = Artifacts.load(project_root)
    else:
        artifacts = Artifacts()
    
    return AppContext(
        project_root=project_root,
        base_dir=BASE_DIR,
        comfy_dir=COMFY_DIR,
        cmd=SubprocessRunner(),
        state=FileStateManager(BASE_DIR),
        artifacts=artifacts,
        debug=debug,
        addon_manifests=load_manifests(project_root),
    )


def execute(
    action: str, 
    context: AppContext, 
    until: Optional[str] = None,
    only: Optional[str] = None,
) -> None:
    """
    执行插件 Pipeline
    
    Args:
        action: 生命周期动作 (setup/start/sync)
        context: 应用上下文
        until: 执行到指定插件为止（包含）
        only: 只执行指定插件（跳过依赖，危险模式）
    """
    pipeline = create_pipeline()
    
    # sync 动作逆序执行
    if action == "sync":
        pipeline = list(reversed(pipeline))
    
    # --only: 只执行单个插件
    if only:
        addon = next((a for a in pipeline if a.name == only), None)
        if not addon:
            logger.error(f"未知插件: {only}")
            sys.exit(1)
        
        logger.info(f"\n>>> 单独执行: {addon.name}.{action}()")
        method = getattr(addon, action, None)
        if method:
            method(context)
        return
    
    # 正常顺序执行
    logger.info(f"\n>>> 开始执行 Pipeline: [{action.upper()}]")
    
    for addon in pipeline:
        logger.info(f"  -> {addon.name}")
        method = getattr(addon, action, None)
        if method:
            method(context)
        
        # --until: 执行到指定插件停止
        if until and addon.name == until:
            logger.info(f"  -> 已到达目标插件 [{until}]，停止")
            break
    
    # setup 完成后持久化 artifacts，供后续 start/sync 使用
    if action == "setup":
        try:
            context.artifacts.save(context.project_root)
            logger.info("  -> Artifacts 已持久化")
        except Exception as e:
            logger.error(f"  -> Artifacts 持久化失败: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL 自动化装配调度器")
    parser.add_argument("action", choices=["setup", "start", "sync"], help="生命周期动作")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--until", type=str, help="执行到指定插件为止")
    parser.add_argument("--only", type=str, help="只执行指定插件（危险模式）")
    args = parser.parse_args()

    # 初始化日志（必须在所有其他操作之前）
    log_file = BASE_DIR / "autodl-setup.log"
    setup_logger(log_file, debug=args.debug)

    # 清理残留进程
    kill_process_by_name("python.*src.main", exclude_pid=os.getpid())

    # 初始化网络环境 (代理 + 镜像 + Token)
    setup_network()

    # 创建上下文并执行
    # start/sync 需要加载 setup 阶段持久化的 artifacts
    load_artifacts = args.action in ("start", "sync")
    context = create_context(debug=args.debug, load_artifacts=load_artifacts)

    # sync 阶段：先将 mihomo 运行时配置同步回持久化目录
    # 必须在 execute 之前，因为 userdata addon 的 sync 会 git add . && push
    if args.action == "sync":
        sync_proxy_config()

    execute(args.action, context, until=args.until, only=args.only)


if __name__ == "__main__":
    main()