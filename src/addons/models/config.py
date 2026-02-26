"""
模型路径配置

从 extra_model_paths.yaml 读取模型存储路径配置
"""
from pathlib import Path
from typing import Any, Dict, Optional, cast

from src.lib.utils import load_yaml


# ============================================================
# 路径常量
# ============================================================
ADDON_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADDON_DIR.parent.parent.parent
PRESETS_FILE = ADDON_DIR / "manifest.yaml"
LOCK_FILE = PROJECT_ROOT / "my-comfyui-backup" / "model_lock.yaml"
EXTRA_PATHS_FILE = ADDON_DIR / "extra_model_paths.yaml"


# ============================================================
# 配置函数
# ============================================================
def get_extra_paths_config() -> Dict[str, Any]:
    """从 extra_model_paths.yaml 获取配置的第一个 section"""
    config = load_yaml(EXTRA_PATHS_FILE)
    for section_value in config.values():
        if isinstance(section_value, dict):
            return cast(Dict[str, Any], section_value)
    return {}


def get_models_base(fallback: Optional[Path] = None) -> Optional[Path]:
    """从 extra_model_paths.yaml 获取模型根目录。

    优先读取 extra_model_paths.yaml 中的 base_path，
    未配置时返回 fallback（默认为 None，调用方需自行处理）。
    """
    section = get_extra_paths_config()
    base_path = section.get("base_path", "")
    if isinstance(base_path, str) and base_path:
        return Path(base_path)
    return fallback


def get_type_dir_mapping() -> Dict[str, str]:
    """从 extra_model_paths.yaml 获取 类型 -> 目录 映射"""
    section = get_extra_paths_config()
    mapping: Dict[str, str] = {}
    for key, value in section.items():
        if key == "base_path":
            continue
        if isinstance(value, str):
            mapping[key] = value.rstrip("/")
    return mapping


def resolve_type_to_dir(type_or_path: str) -> str:
    """将类型名或路径解析为目标目录
    
    Args:
        type_or_path: 类型名 (如 "lora") 或子路径 (如 "clip/flux")
        
    Returns:
        解析后的目录路径
    """
    # 如果已经是路径，直接返回
    if "/" in type_or_path:
        return type_or_path
    
    mapping = get_type_dir_mapping()
    
    # 精确匹配
    if type_or_path in mapping:
        return mapping[type_or_path]
    
    # 大小写不敏感匹配
    type_lower = type_or_path.lower()
    for key, value in mapping.items():
        if key.lower() == type_lower:
            return value
    
    # 未找到，返回原值作为目录
    return type_or_path