"""
核心接口定义
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pluggy

from src.core.ports import ICommandRunner, IStateManager
from src.core.artifacts import Artifacts


hookspec = pluggy.HookspecMarker("autodl_env")
hookimpl = pluggy.HookimplMarker("autodl_env")


@dataclass
class AppContext:
    """
    应用上下文 - 组合根
    
    所有插件都通过这个上下文获取输入、执行操作、存储产出。
    """
    
    # === 基础路径（main.py 注入，不可变）===
    project_root: Path
    base_dir: Path      # /root/autodl-tmp (数据盘)
    comfy_dir: Path     # /root/ComfyUI (系统盘)
    
    # === 注入的服务 ===
    cmd: ICommandRunner
    state: IStateManager
    
    # === 插件产出（强类型）===
    artifacts: Artifacts = field(default_factory=Artifacts)
    
    # === 运行时参数 ===
    debug: bool = False
    
    # === 执行追踪（用于调试和测试）===
    execution_log: List[str] = field(default_factory=lambda: [])
    
    # === 预加载的 Manifest（避免插件直接读文件）===
    addon_manifests: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {})


# 兼容别名
Context = AppContext


class BaseAddon:
    """插件基类
    
    子类必须声明 module_dir 类属性（= 所在目录名），
    name 属性由基类统一从 module_dir 派生，子类无需覆盖。
    """
    
    # 子类必须声明，值 = 插件所在目录名
    module_dir: str
    
    @property
    def name(self) -> str:
        """插件唯一标识 = 所在目录名，由 module_dir 派生"""
        return self.module_dir
    
    def log(self, context: AppContext, action: str, message: str = "") -> None:
        """记录执行日志"""
        log_entry = f"{self.name}:{action}"
        if message:
            log_entry += f":{message}"
        context.execution_log.append(log_entry)
    
    def get_manifest(self, context: AppContext) -> Dict[str, Any]:
        """获取当前插件的 manifest 配置"""
        return context.addon_manifests.get(self.name, {})
    
    def get_addon_dir(self, context: AppContext) -> Path:
        """获取当前插件的目录路径"""
        return context.project_root / "src" / "addons" / self.name

    @hookspec
    def setup(self, context: AppContext) -> None:
        """初始化钩子"""
        ...
    
    @hookspec
    def start(self, context: AppContext) -> None:
        """启动钩子"""
        ...
    
    @hookspec
    def sync(self, context: AppContext) -> None:
        """同步钩子"""
        ...
