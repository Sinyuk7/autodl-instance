"""
通用工具函数
"""
import hashlib
from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    """加载 YAML 文件"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: Dict[str, Any]) -> None:
    """保存 YAML 文件"""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def sha256(file_path: Path) -> str:
    """计算文件 SHA256 哈希"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def format_size(size_kb: int) -> str:
    """格式化文件大小 (KB -> 人类可读)"""
    if size_kb < 1024:
        return f"{size_kb} KB"
    elif size_kb < 1024 * 1024:
        return f"{size_kb / 1024:.1f} MB"
    else:
        return f"{size_kb / 1024 / 1024:.2f} GB"
