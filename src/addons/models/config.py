"""
模型路径配置

提供模型目录路径工具函数。
采用软链接方案后，不再需要 extra_model_paths.yaml 配置。
"""
import os
from pathlib import Path
from typing import List


# ============================================================
# 路径常量
# ============================================================
ADDON_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADDON_DIR.parent.parent.parent
PRESETS_FILE = ADDON_DIR / "manifest.yaml"
USERDATA_DIR_NAME = "my-comfyui-backup"
LOCK_FILE_NAME = "model-lock.yaml"

# 与 main.py 保持一致的基础目录
_BASE_DIR = Path("/root/autodl-tmp")
_MODELS_DIR_NAME = "models"


def get_lock_file(project_root: Path | None = None) -> Path:
    """获取 Git 可同步的 model-lock.yaml 路径。"""
    root = project_root or PROJECT_ROOT
    return root / USERDATA_DIR_NAME / LOCK_FILE_NAME


def get_legacy_lock_file(base_dir: Path | None = None) -> Path:
    """获取旧版本写入的数据盘根目录 lock 路径，用于一次性兼容读取。"""
    base = base_dir or _BASE_DIR
    return base / LOCK_FILE_NAME


LOCK_FILE = get_lock_file()


# ============================================================
# 配置函数
# ============================================================
def get_models_base(fallback: Path | None = None) -> Path:
    """获取模型根目录。

    优先读取环境变量 COMFYUI_MODELS_DIR，
    否则使用 /root/autodl-tmp/models/ 目录。
    
    采用软链接方案后，此目录与 ComfyUI/models/ 等价。
    """
    # 1. 优先使用环境变量
    env_path = os.environ.get("COMFYUI_MODELS_DIR")
    if env_path:
        return Path(env_path)
    
    # 2. 测试或诊断可传入 fallback
    if fallback is not None:
        return fallback

    # 3. 默认使用 /root/autodl-tmp/models/ (与 main.py BASE_DIR 一致)
    return _BASE_DIR / _MODELS_DIR_NAME


def get_available_types() -> List[str]:
    """获取可用的模型类型（扫描实际目录结构）
    
    Returns:
        模型目录下的子目录名列表，如 ["checkpoints", "loras", "LLM", ...]
    """
    base = get_models_base()
    if not base.exists():
        return []
    return sorted([d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")])


def resolve_type_to_dir(type_or_path: str) -> str:
    """将类型名或路径解析为目标目录
    
    采用软链接方案后，直接返回输入（路径透传）。
    用户可以使用任意子目录路径，如 "LLM/Qwen-VL"。
    
    Args:
        type_or_path: 类型名 (如 "loras") 或子路径 (如 "LLM/Qwen-VL")
        
    Returns:
        原样返回输入路径
    """
    return type_or_path
