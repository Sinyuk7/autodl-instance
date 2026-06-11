"""
API Token 管理 - HuggingFace / CivitAI 等
"""
import logging
import os
from typing import Any, Dict, List, cast

from src.core.runtime import load_local_secrets
from src.lib.network.config import ENV_HF_TOKEN, ENV_CIVITAI_TOKEN

logger = logging.getLogger("autodl_setup")


def load_api_tokens(verbose: bool = True) -> None:
    """从本机 secrets.yaml 加载 API Token。"""
    secrets_config = load_local_secrets()

    api_keys_raw = secrets_config.get("api_keys", {})
    if not isinstance(api_keys_raw, dict):
        api_keys_raw = {}
    api_keys = cast(Dict[str, Any], api_keys_raw)

    tokens_loaded: List[str] = []

    # HuggingFace Token (HF_TOKEN 是 huggingface_hub 官方标准)
    hf_token = secrets_config.get("hf_token") or api_keys.get("hf_api_token")
    if isinstance(hf_token, str) and hf_token:
        os.environ.setdefault(ENV_HF_TOKEN, hf_token)
        tokens_loaded.append(ENV_HF_TOKEN)

    # CivitAI Token
    civitai_token = secrets_config.get("civitai_token") or api_keys.get("civitai_api_token")
    if isinstance(civitai_token, str) and civitai_token:
        os.environ.setdefault(ENV_CIVITAI_TOKEN, civitai_token)
        tokens_loaded.append(ENV_CIVITAI_TOKEN)

    if verbose and tokens_loaded:
        logger.info(f"  -> ✓ API Token 已加载: {', '.join(tokens_loaded)}")
