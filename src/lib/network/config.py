"""
网络模块配置常量

集中管理路径、环境变量 Key、导出列表等。
"""
from pathlib import Path
from typing import List

from src.core.schema import EnvKey

# ── 环境变量 Key ────────────────────────────────────────────
ENV_HF_TOKEN = EnvKey.HF_TOKEN
ENV_HF_ENDPOINT = EnvKey.HF_ENDPOINT
ENV_CIVITAI_TOKEN = EnvKey.CIVITAI_API_TOKEN

# ── 项目根目录 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── AutoDL 学术加速 ────────────────────────────────────────
AUTODL_TURBO_SCRIPT = Path("/etc/network_turbo")

AUTODL_TURBO_KEYS = [
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY",
    "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE",
]

# ── 需要导出到用户 shell 的环境变量 ────────────────────────
EXPORT_KEYS: List[str] = [
    # 代理
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY",
    "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE",
    # HuggingFace
    EnvKey.HF_ENDPOINT, EnvKey.HF_TOKEN,
    # CivitAI
    EnvKey.CIVITAI_API_TOKEN,
]
