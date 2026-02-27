"""
NetworkManager - 网络环境核心编排器

按顺序初始化所有网络子模块: turbo → mirror → token
"""
import logging
import os
from typing import List, Optional

from src.lib.network.config import EXPORT_KEYS
from src.lib.network.turbo import load_autodl_turbo
from src.lib.network.mirror import load_hf_mirror
from src.lib.network.token import load_api_tokens

logger = logging.getLogger("autodl_setup")


class NetworkManager:
    """网络环境管理器"""

    def __init__(self) -> None:
        self._initialized = False

    def setup(self, verbose: bool = True) -> None:
        """初始化网络环境 (仅执行一次)

        Args:
            verbose: 是否输出日志，独立脚本可设为 False
        """
        if self._initialized:
            return

        if verbose:
            logger.info("\n>>> [Network] 正在初始化网络环境...")

        # 1. 加载 AutoDL 学术加速
        load_autodl_turbo(verbose)

        # 2. 加载 HuggingFace 镜像配置
        load_hf_mirror(verbose)

        # 3. 加载 API Token
        load_api_tokens(verbose)

        self._initialized = True


# ── 全局单例 ────────────────────────────────────────────────
_network_manager: Optional[NetworkManager] = None


def setup_network(verbose: bool = True) -> None:
    """初始化网络环境 (全局入口)

    Args:
        verbose: 是否输出日志，main.py 中设为 True，独立脚本可设为 False
    """
    global _network_manager
    if _network_manager is None:
        _network_manager = NetworkManager()
    _network_manager.setup(verbose)


def export_env_shell() -> str:
    """执行 setup_network() 后，输出所有网络相关环境变量的 export 语句。

    供 bin/turbo 使用: eval $(python -m src.lib.network)
    这样 network 模块就是 bash 和 Python 两个世界的唯一真相来源。
    """
    setup_network(verbose=False)

    lines: List[str] = []
    for key in EXPORT_KEYS:
        value = os.environ.get(key)
        if value:
            # 转义单引号，防止注入
            safe_value = value.replace("'", "'\\''")
            lines.append(f"export {key}='{safe_value}'")

    return "\n".join(lines)
