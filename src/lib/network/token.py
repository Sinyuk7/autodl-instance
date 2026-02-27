"""
API Token 管理 - HuggingFace / CivitAI 等
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, cast

import yaml

from src.lib.network.config import ENV_HF_TOKEN, ENV_CIVITAI_TOKEN, PROJECT_ROOT

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


def load_api_tokens(verbose: bool = True) -> None:
    """从 download/secrets.yaml 加载 API Token"""
    secrets_config = _load_yaml(PROJECT_ROOT / "src" / "lib" / "download" / "secrets.yaml")

    api_keys_raw = secrets_config.get("api_keys", {})
    if not isinstance(api_keys_raw, dict):
        return
    api_keys = cast(Dict[str, Any], api_keys_raw)

    tokens_loaded: List[str] = []

    # HuggingFace Token (HF_TOKEN 是 huggingface_hub 官方标准)
    hf_token = api_keys.get("hf_api_token")
    if isinstance(hf_token, str) and hf_token:
        os.environ.setdefault(ENV_HF_TOKEN, hf_token)
        tokens_loaded.append(ENV_HF_TOKEN)

    # CivitAI Token
    civitai_token = api_keys.get("civitai_api_token")
    if isinstance(civitai_token, str) and civitai_token:
        os.environ.setdefault(ENV_CIVITAI_TOKEN, civitai_token)
        tokens_loaded.append(ENV_CIVITAI_TOKEN)

    if verbose and tokens_loaded:
        logger.info(f"  -> ✓ API Token 已加载: {', '.join(tokens_loaded)}")
