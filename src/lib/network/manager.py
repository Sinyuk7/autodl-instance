"""
NetworkManager - 网络环境核心编排器

按顺序初始化所有网络子模块: proxy → mirror → token

代理策略:
  1. 如果配置了 mihomo（proxy/secrets.yaml 有 subscription_url）→ 启动 mihomo
  2. 否则 fallback 到 AutoDL 学术加速（/etc/network_turbo）
  3. 都没有 → 无代理模式
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.lib.network.config import EXPORT_KEYS
from src.lib.network.turbo import load_autodl_turbo
from src.lib.network.mirror import load_hf_mirror
from src.lib.network.token import load_api_tokens
from src.lib.network.proxy import ProxyConfig, MihomoBackend

logger = logging.getLogger("autodl_setup")

# 配置文件路径
_PROXY_DIR = Path(__file__).resolve().parent / "proxy"
_PROXY_MANIFEST = _PROXY_DIR / "manifest.yaml"
_PROXY_SECRETS = _PROXY_DIR / "secrets.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    """安全加载 YAML 文件"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _build_proxy_config() -> Optional[ProxyConfig]:
    """从 manifest.yaml + secrets.yaml 构建 ProxyConfig

    Returns:
        ProxyConfig 实例，如果未配置订阅地址则返回 None
    """
    secrets = _load_yaml(_PROXY_SECRETS)
    subscription_url = secrets.get("subscription_url", "")

    if not subscription_url:
        return None

    manifest = _load_yaml(_PROXY_MANIFEST)

    return ProxyConfig(
        subscription_url=subscription_url,
        proxy_port=manifest.get("proxy_port", 7890),
        api_port=manifest.get("api_port", 9090),
        api_secret=secrets.get("api_secret", ""),
        version=manifest.get("mihomo_version", "v1.19.10"),
        install_dir=Path(manifest.get("install_dir", "/usr/local/bin")),
        config_dir=Path(manifest.get("config_dir", "/etc/mihomo")),
    )


def _inject_proxy_env(proxy_url: str) -> None:
    """将代理地址注入到当前进程环境变量"""
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url

    # AutoDL 内网和 localhost 不走代理
    no_proxy = "localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["no_proxy"] = no_proxy
    os.environ["NO_PROXY"] = no_proxy

    logger.info(f"  -> ✓ 代理环境变量已注入: {proxy_url}")


class NetworkManager:
    """网络环境管理器"""

    def __init__(self) -> None:
        self._initialized = False
        self._backend: Optional[MihomoBackend] = None

    def setup(self, verbose: bool = True) -> None:
        """初始化网络环境 (仅执行一次)

        Args:
            verbose: 是否输出日志，独立脚本可设为 False
        """
        if self._initialized:
            return

        if verbose:
            logger.info("\n>>> [Network] 正在初始化网络环境...")

        # 1. 代理 — 决定用 mihomo 还是 turbo
        self._setup_proxy(verbose)

        # 2. 加载 HuggingFace 镜像配置
        load_hf_mirror(verbose)

        # 3. 加载 API Token
        load_api_tokens(verbose)

        self._initialized = True

    def _setup_proxy(self, verbose: bool) -> None:
        """代理初始化

        策略:
          1. 有 mihomo 配置 → 先用 turbo 引导下载，再切到 mihomo
          2. 没有 mihomo 配置 → 直接用 turbo 兜底
        """
        config = _build_proxy_config()

        if config is None:
            # 没有配置 mihomo，用 turbo 兜底
            load_autodl_turbo(verbose)
            return

        if verbose:
            logger.info("  -> 检测到 mihomo 代理配置，准备启动...")

        # 先加载 turbo 作为引导网络（下载 mihomo 内核和订阅需要网络）
        load_autodl_turbo(verbose=False)

        backend = MihomoBackend(config)

        # 安装内核
        if not backend.install():
            if verbose:
                logger.warning("  -> [WARN] mihomo 安装失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            return

        # 下载/更新订阅
        if not backend.update_subscription():
            if verbose:
                logger.warning("  -> [WARN] 订阅更新失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            return

        # 启动代理
        if not backend.start():
            if verbose:
                logger.warning("  -> [WARN] mihomo 启动失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            return

        # 健康检查
        if backend.health_check():
            if verbose:
                logger.info("  -> ✓ mihomo 代理连通性测试通过")
        else:
            if verbose:
                logger.warning("  -> [WARN] mihomo 连通性测试未通过，但进程已启动")

        # 切换环境变量到 mihomo（覆盖 turbo）
        _inject_proxy_env(config.proxy_url)

        self._backend = backend

    def stop_proxy(self) -> None:
        """停止代理进程（供关机/清理时调用）"""
        if self._backend:
            self._backend.stop()
            self._backend = None


# ── 全局单例 ────────────────────────────────────────────────
_network_manager: Optional[NetworkManager] = None


def get_network_manager() -> NetworkManager:
    """获取全局 NetworkManager 实例"""
    global _network_manager
    if _network_manager is None:
        _network_manager = NetworkManager()
    return _network_manager


def setup_network(verbose: bool = True) -> None:
    """初始化网络环境 (全局入口)

    Args:
        verbose: 是否输出日志，main.py 中设为 True，独立脚本可设为 False
    """
    get_network_manager().setup(verbose)


def stop_proxy() -> None:
    """停止代理进程 (全局入口，供 shutdown 脚本调用)"""
    get_network_manager().stop_proxy()


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
