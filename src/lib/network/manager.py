"""
NetworkManager - 网络环境核心编排器

按顺序初始化所有网络子模块: proxy → mirror → token

代理策略:
  1. 如果配置了 mihomo（autodl secrets 有 mihomo_subscription_url，
     或 workspace/mihomo/ 有手动上传的配置）→ 启动 mihomo
  2. 否则 fallback 到 AutoDL 学术加速（/etc/network_turbo）
  3. 都没有 → 无代理模式

配置持久化:
  mihomo 配置通过本地 workspace/mihomo/ 目录持久化到数据盘。
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.lib.network.config import EXPORT_KEYS
from src.lib.network.turbo import load_autodl_turbo
from src.lib.network.mirror import load_hf_mirror
from src.lib.network.token import load_api_tokens
from src.lib.network.proxy import ProxyConfig, MihomoBackend
from src.lib.network.state import (
    get_cached_network_decision,
    cache_network_decision,
    is_subscription_recently_failed,
    mark_subscription_failed,
    mark_subscription_success,
    invalidate_cache,
)
from src.core.runtime import load_local_secrets, resolve_runtime_config

logger = logging.getLogger("autodl_setup")

# 配置文件路径
_PROXY_DIR = Path(__file__).resolve().parent / "proxy"
_PROXY_MANIFEST = _PROXY_DIR / "manifest.yaml"

_WORKSPACE_MIHOMO_DIR = "mihomo"

# 需要在本地 workspace ↔ /etc/mihomo 之间持久化的文件
_SYNC_FILES = [
    "config.yaml",   # Clash 订阅配置
    "cache.db",      # 节点选择记录（mihomo 自动生成）
]


def _load_yaml(path: Path) -> Dict[str, Any]:
    """安全加载 YAML 文件"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_workspace_mihomo_dir() -> Path:
    """获取 mihomo 本地 workspace 持久化目录"""
    code_root = Path(__file__).resolve().parent.parent.parent.parent
    return resolve_runtime_config(code_root).workspace_data_dir / _WORKSPACE_MIHOMO_DIR


def _get_local_secrets() -> Dict[str, Any]:
    code_root = Path(__file__).resolve().parent.parent.parent.parent
    runtime = resolve_runtime_config(code_root)
    return load_local_secrets(runtime.secrets_file)


def _build_proxy_config() -> Optional[ProxyConfig]:
    """从 package manifest + 本机 secrets 构建 ProxyConfig

    判断是否启用 mihomo 的条件（满足任一即可）:
    1. 本机 secrets 中配置了 mihomo_subscription_url（在线订阅模式）
    2. workspace 目录中存在 config.yaml（手动配置模式）

    Returns:
        ProxyConfig 实例，如果两个条件都不满足则返回 None
    """
    secrets = _get_local_secrets()
    subscription_url = (
        secrets.get("mihomo_subscription_url")
        or secrets.get("subscription_url")
        or ""
    )

    # 检查 workspace 是否有手动配置
    workspace_config = _get_workspace_mihomo_dir() / "config.yaml"
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

    def _restore_from_workspace(self, config: ProxyConfig) -> bool:
        """从本地 workspace 恢复 mihomo 配置到运行时目录

        Args:
            config: 代理配置

        Returns:
            True 表示成功恢复了配置
        """
        workspace_dir = _get_workspace_mihomo_dir()
        workspace_config = workspace_dir / "config.yaml"

        if not workspace_config.exists() or workspace_config.stat().st_size < 100:
            return False

        config.config_dir.mkdir(parents=True, exist_ok=True)

        # 复制所有同步文件
        restored: List[str] = []
        for filename in _SYNC_FILES:
            src = workspace_dir / filename
            if src.exists() and src.stat().st_size > 0:
                dst = config.config_dir / filename
                shutil.copy2(src, dst)
                restored.append(filename)

        if restored:
            logger.info(
                f"  -> ✓ 从持久化目录恢复配置: {', '.join(restored)}"
            )
            return True
        return False

    def _persist_config(self, config: ProxyConfig) -> None:
        """将运行时配置写入本地 workspace

        Args:
            config: 代理配置
        """
        workspace_dir = _get_workspace_mihomo_dir()
        runtime_config = config.config_dir / "config.yaml"

        if not runtime_config.exists() or runtime_config.stat().st_size < 100:
            return

        workspace_dir.mkdir(parents=True, exist_ok=True)

        for filename in _SYNC_FILES:
            src = config.config_dir / filename
            if src.exists() and src.stat().st_size > 0:
                dst = workspace_dir / filename
                shutil.copy2(src, dst)

        logger.debug(f"  -> 配置已写入 workspace: {workspace_dir}")

    def _setup_proxy(self, verbose: bool) -> None:
        """代理初始化 (带状态缓存加速)

        策略:
          1. 快速路径: 检查跨进程缓存，如果上次决策仍有效则直接复用
          2. 有 mihomo 配置 → 先用 turbo 引导下载，再切到 mihomo
          3. 没有 mihomo 配置 → 直接用 turbo 兜底

        配置来源优先级:
          1. workspace 已有配置 → 恢复到运行时目录
          2. subscription_url 在线下载 → 写入 workspace
        """
        # ── 快速路径: 尝试复用上次的网络决策 ──
        if self._try_fast_path(verbose):
            return

        config = _build_proxy_config()

        if config is None:
            # 没有配置 mihomo，用 turbo 兜底
            load_autodl_turbo(verbose)
            cache_network_decision("turbo")
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
            cache_network_decision("turbo")
            return

        # 从 workspace 恢复配置到 /etc/mihomo/
        self._restore_from_workspace(config)

        # 订阅更新 — 利用失败缓存避免重复尝试
        if is_subscription_recently_failed():
            if verbose:
                logger.info("  -> 订阅近期更新失败，跳过重试 (30 分钟内自动重置)")
            # 检查是否有可用的本地配置可以继续
            config_file = config.config_dir / "config.yaml"
            if not (config_file.exists() and config_file.stat().st_size > 100):
                if verbose:
                    logger.warning("  -> [WARN] 无可用本地配置，回退到 AutoDL 学术加速")
                load_autodl_turbo(verbose)
                cache_network_decision("turbo")
                return
            # 有本地配置，修补后继续启动 mihomo
            from src.lib.network.proxy.config import patch_config
            patch_config(config, config_file)
        elif not backend.update_subscription():
            # 订阅更新首次失败，写入失败标记
            mark_subscription_failed()
            if verbose:
                logger.warning("  -> [WARN] 订阅更新失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            cache_network_decision("turbo")
            return
        else:
            # 订阅更新成功，清除失败标记
            mark_subscription_success()

        # 启动成功前的配置已经就绪，写入 workspace
        self._persist_config(config)

        # 启动代理
        if not backend.start():
            if verbose:
                logger.warning("  -> [WARN] mihomo 启动失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            cache_network_decision("turbo")
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
        cache_network_decision("mihomo")

        self._backend = backend

    def _try_fast_path(self, verbose: bool) -> bool:
        """快速路径: 利用跨进程缓存复用上次的网络决策

        当另一个进程（如 main.py 的 setup）已经完成网络初始化后，
        后续短生命周期进程（如 model download）可以直接复用决策结果，
        跳过耗时的 mihomo 安装→订阅→启动→健康检查流程。

        快速路径条件:
          - 缓存未过期
          - 决策为 "turbo" → 直接加载 turbo 即可
          - 决策为 "mihomo" → 检查 mihomo 进程是否还在运行

        Returns:
            True 表示快速路径命中，已完成代理初始化
        """
        cached = get_cached_network_decision()
        if cached is None:
            return False

        if cached == "turbo":
            # 上次决策是 turbo，直接加载
            load_autodl_turbo(verbose)
            if verbose:
                logger.debug("  -> [快速路径] 复用 turbo 决策缓存")
            return True

        if cached == "mihomo":
            # 上次决策是 mihomo，检查进程是否仍在运行
            config = _build_proxy_config()
            if config is None:
                # 配置已被删除，缓存失效
                invalidate_cache()
                return False

            backend = MihomoBackend(config)
            if backend.is_running():
                # mihomo 进程仍在运行，直接注入环境变量
                _inject_proxy_env(config.proxy_url)
                self._backend = backend
                if verbose:
                    logger.info(
                        f"  -> ✓ mihomo 代理已就绪 (Proxy: {config.proxy_url})"
                    )
                return True
            else:
                # mihomo 进程已退出，缓存失效，需要完整重启
                invalidate_cache()
                return False

        return False

    def stop_proxy(self) -> None:
        """停止代理进程（供关机/清理时调用）"""
        if self._backend:
            self._backend.stop()
            self._backend = None

    def persist_config(self) -> None:
        """将运行时 mihomo 配置持久化到本地 workspace。"""
        config = _build_proxy_config()
        if config is None:
            return

        workspace_dir = _get_workspace_mihomo_dir()
        runtime_config = config.config_dir / "config.yaml"

        if not runtime_config.exists():
            return

        workspace_dir.mkdir(parents=True, exist_ok=True)

        persisted: List[str] = []
        for filename in _SYNC_FILES:
            src = config.config_dir / filename
            if src.exists() and src.stat().st_size > 0:
                dst = workspace_dir / filename
                # 只在内容变化时复制（避免无意义的 git diff）
                if dst.exists() and dst.read_bytes() == src.read_bytes():
                    continue
                shutil.copy2(src, dst)
                persisted.append(filename)

        if persisted:
            logger.info(f"  -> mihomo 配置已写入本地 workspace: {', '.join(persisted)}")
        else:
            logger.debug("  -> mihomo 配置无变更，跳过写入")


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
