"""
镜像源管理 - HuggingFace 镜像等
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from src.lib.network.config import ENV_HF_ENDPOINT, PROJECT_ROOT

logger = logging.getLogger("autodl_setup")


def _load_yaml(path: Path) -> Dict[str, Any]:
    """安全加载 YAML 文件"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_hf_mirror(verbose: bool = True) -> None:
    """加载 HuggingFace 镜像配置"""
    # 如果已设置环境变量，跳过
    existing = os.environ.get(ENV_HF_ENDPOINT)
    if existing:
        if verbose:
            logger.info(f"  -> ✓ HF 镜像: {existing} (环境变量)")
        return

    # 从 system/manifest.yaml 读取配置
    system_config = _load_yaml(PROJECT_ROOT / "src" / "addons" / "system" / "manifest.yaml")
    hf_mirror = system_config.get("huggingface_mirror")

    if hf_mirror and isinstance(hf_mirror, str):
        os.environ[ENV_HF_ENDPOINT] = hf_mirror
        if verbose:
            logger.info(f"  -> ✓ HF 镜像: {hf_mirror}")
    else:
        if verbose:
            logger.info("  -> ✗ HF 镜像: 未配置 (使用官方源，可能限速)")
