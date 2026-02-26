"""
Artifacts - 插件间共享的强类型数据容器
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Artifacts:
    """
    插件产出的强类型容器。
    
    这是一个纯数据对象（DTO），新增插件时需要在此添加对应字段。
    这是有意的设计，目的是：
    - 强制声明插件的输入输出契约
    - 编译时类型检查
    - IDE 自动补全
    """
    
    # ==================== ComfyAddon ====================
    comfy_dir: Optional[Path] = None
    custom_nodes_dir: Optional[Path] = None
    user_dir: Optional[Path] = None
    
    # ==================== NodesAddon ====================
    snapshots_dir: Optional[Path] = None
    latest_snapshot: Optional[Path] = None
    
    # ==================== UserdataAddon ====================
    userdata_dir: Optional[Path] = None
    
    # ==================== ModelAddon ====================
    models_dir: Optional[Path] = None
    extra_model_paths_file: Optional[Path] = None
    
    # ==================== SystemAddon ====================
    bin_dir: Optional[Path] = None
    ssh_dir: Optional[Path] = None
    uv_bin: Optional[Path] = None
    
    # ==================== TorchAddon ====================
    torch_installed: bool = False
    cuda_version: Optional[str] = None
