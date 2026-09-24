"""
NetworkManager - 网络环境核心编排器

按顺序初始化所有网络子模块: proxy → mirror → token

代理策略:
  1. 如果配置了 mihomo（autodl secrets 有 mihomo_subscription_url，
     或 ~/.config/autodl-instance/mihomo/ 有手动上传的配置）→ 启动 mihomo
  2. 否则 fallback 到 AutoDL 学术加速（/etc/network_turbo）
  3. 都没有 → 无代理模式

配置持久化:
  mihomo 配置通过本地 ~/.config/autodl-instance/mihomo/ 目录持久化到系统盘。
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.lib.network.policy import (PROXY_KEYS, read_mode, clear_proxy_environment, proxy_environment, shell_environment)
from src.lib.network.turbo import load_autodl_turbo
from src.lib.network.mirror import load_hf_mirror
from src.lib.network.token import load_api_tokens
from src.lib.network.proxy import ProxyConfig, MihomoBackend
from src.lib.network.state import (
    cache_network_decision,
    is_subscription_recently_failed,
    mark_subscription_failed,
    mark_subscription_success,
)
from src.core.runtime import DEFAULT_CONFIG_FILE, load_local_secrets, resolve_runtime_config

logger = logging.getLogger("autodl_setup")

# 配置文件路径
_PROXY_DIR = Path(__file__).resolve().parent / "proxy"
_PROXY_MANIFEST = _PROXY_DIR / "manifest.yaml"

_WORKSPACE_MIHOMO_DIR = "mihomo"

def _load_yaml(path: Path) -> Dict[str, Any]:
    """安全加载 YAML 文件"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_workspace_mihomo_dir(config_file: Path = DEFAULT_CONFIG_FILE) -> Path:
    """获取 mihomo 本地 workspace 持久化目录"""
    return config_file.parent / _WORKSPACE_MIHOMO_DIR


def _get_local_secrets(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    code_root = Path(__file__).resolve().parent.parent.parent.parent
    runtime = resolve_runtime_config(code_root, config_file=config_file)
    return load_local_secrets(runtime.secrets_file)


def _build_proxy_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Optional[ProxyConfig]:
    """从 package manifest + 本机 secrets 构建 ProxyConfig

    判断是否启用 mihomo 的条件（满足任一即可）:
    1. 本机 secrets 中配置了 mihomo_subscription_url（在线订阅模式）
    2. workspace 目录中存在 config.yaml（手动配置模式）

    Returns:
        ProxyConfig 实例，如果两个条件都不满足则返回 None
    """
    secrets = _get_local_secrets(config_file)
    subscription_url = (
        secrets.get("mihomo_subscription_url")
        or secrets.get("subscription_url")
        or ""
    )

    # 检查 workspace 是否有手动配置
    workspace_config = _get_workspace_mihomo_dir(config_file) / "config.yaml"
    has_workspace_config = workspace_config.exists() and workspace_config.stat().st_size > 100

    if not subscription_url and not has_workspace_config:
        return None

    manifest = _load_yaml(_PROXY_MANIFEST)

    return ProxyConfig(
        subscription_url=subscription_url,
        proxy_port=manifest.get("proxy_port", 7890),
        api_port=manifest.get("api_port", 9090),
        api_secret=secrets.get("mihomo_api_secret") or secrets.get("api_secret", ""),
        version=manifest.get("mihomo_version", "v1.19.10"),
        install_dir=Path(manifest.get("install_dir", "/usr/local/bin")),
        # The workspace directory is the single source of truth.  Passing it
        # directly to mihomo avoids accidental $PWD-based empty configs and
        # avoids copying private proxy profiles between storage locations.
        config_dir=_get_workspace_mihomo_dir(config_file).resolve(),
    )


def _inject_proxy_env(proxy_url: str) -> None:
    """将代理地址注入到当前进程环境变量"""
    os.environ.update(proxy_environment(proxy_url))
    logger.info("  -> ✓ 当前进程及后续子进程已配置 Mihomo 代理")



class NetworkManager:
    """网络环境管理器"""

    def __init__(self, config_file: Path = DEFAULT_CONFIG_FILE, *, proxy_mode: Optional[str] = None) -> None:
        self._config_file = config_file
        self._mode_override = proxy_mode
        self._last_mode: Optional[str] = None
        self._initialized = False
        self._backend: Optional[MihomoBackend] = None

    def setup(self, verbose: bool = True) -> None:
        """初始化网络环境 (仅执行一次)

        Args:
            verbose: 是否输出日志，独立脚本可设为 False
        """
        mode = self._mode_override or read_mode(self._config_file)
        if self._initialized and self._last_mode == mode:
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
        self._last_mode = mode

    def _fallback_proxy(self, verbose: bool) -> None:
        if (self._mode_override or read_mode(self._config_file)) == "on":
            clear_proxy_environment()
            raise RuntimeError("Mihomo 不可用；代理开关为 on，拒绝静默回退。请检查 autodl proxy status。")
        load_autodl_turbo(verbose)
        cache_network_decision("turbo" if os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") else "direct")

    def _setup_proxy(self, verbose: bool) -> None:
        """Reuse a healthy owned proxy; otherwise initialize the configured backend."""
        mode = self._mode_override or read_mode(self._config_file)
        if mode == "off":
            clear_proxy_environment()
            cache_network_decision("direct")
            if verbose:
                logger.info("  -> 代理已关闭：直连，不加载 AutoDL 学术加速")
            return
        if mode == "on":
            clear_proxy_environment()
        config = _build_proxy_config(self._config_file)

        if config is None:
            # 没有配置 mihomo，用 turbo 兜底
            self._fallback_proxy(verbose)
            return

        if verbose:
            logger.info("  -> 检测到 mihomo 代理配置，准备启动...")

        backend = MihomoBackend(config)

        if backend.is_running() and backend.health_check():
            _inject_proxy_env(config.proxy_url)
            self._backend = backend
            cache_network_decision("mihomo")
            return

        load_autodl_turbo(verbose=False)

        # 安装内核
        if not backend.install():
            if verbose:
                logger.warning("  -> [WARN] mihomo 安装失败，按代理开关处理失败")
            self._fallback_proxy(verbose)
            return

        # Starting a saved environment must not depend on the subscription server.
        local_config = config.config_dir / "config.yaml"
        if local_config.exists() and local_config.stat().st_size > 100:
            from src.lib.network.proxy.config import patch_config
            patch_config(config, local_config)
        # Only bootstrap from the subscription when no usable saved profile exists.
        elif is_subscription_recently_failed():
            if verbose:
                logger.warning("  -> 无本地配置且订阅近期失败，跳过重试 (30 分钟内自动重置)")
            self._fallback_proxy(verbose)
            return
        elif not backend.update_subscription():
            # 订阅更新首次失败，写入失败标记
            mark_subscription_failed()
            if verbose:
                logger.warning("  -> [WARN] 订阅更新失败，按代理开关处理失败")
            self._fallback_proxy(verbose)
            return
        else:
            # 订阅更新成功，清除失败标记
            mark_subscription_success()

        # 启动代理
        if not backend.start():
            if verbose:
                logger.warning("  -> [WARN] mihomo 启动失败，按代理开关处理失败")
            self._fallback_proxy(verbose)
            return

        # 健康检查
        if not backend.health_check():
            if verbose:
                logger.warning("  -> [WARN] mihomo 连通性测试失败，停止进程并按代理开关处理失败")
            backend.stop()
            self._fallback_proxy(verbose)
            return
        if verbose:
            logger.info("  -> ✓ mihomo 代理连通性测试通过")

        # 切换环境变量到 mihomo（覆盖 turbo）
        _inject_proxy_env(config.proxy_url)
        cache_network_decision("mihomo")

        self._backend = backend

    def stop_proxy(self) -> None:
        """停止代理进程（供关机/清理时调用）"""
        backend = self._backend
        if backend is None:
            config = _build_proxy_config(self._config_file)
            if config is None:
                return
            backend = MihomoBackend(config)
        if not backend.stop():
            raise RuntimeError("Failed to stop owned Mihomo process")
        self._backend = None


# ── 全局单例 ────────────────────────────────────────────────
_network_manager: Optional[NetworkManager] = None


def get_network_manager() -> NetworkManager:
    """获取全局 NetworkManager 实例"""
    global _network_manager
    if _network_manager is None:
        _network_manager = NetworkManager()
    return _network_manager


def setup_network(verbose: bool = True, config_file: Optional[Path] = None) -> None:
    """初始化网络环境 (全局入口)

    Args:
        verbose: 是否输出日志，main.py 中设为 True，独立脚本可设为 False
    """
    if config_file is not None:
        NetworkManager(config_file=config_file).setup(verbose)
        return
    get_network_manager().setup(verbose)


def stop_proxy() -> None:
    """停止代理进程 (全局入口，供 shutdown 脚本调用)"""
    get_network_manager().stop_proxy()


def export_env_shell() -> str:
    """Legacy turbo: initialize networking, export only proxy variables (no tokens)."""
    setup_network(verbose=False)

    mode = read_mode()
    lines: List[str] = [shell_environment()] if mode != "auto" else []
    for key in PROXY_KEYS if mode == "auto" else ():
        value = os.environ.get(key)
        if value:
            # 转义单引号，防止注入
            safe_value = value.replace("'", "'\\''")
            lines.append(f"export {key}='{safe_value}'")

    return "\n".join(lines)
