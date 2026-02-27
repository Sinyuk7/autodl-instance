"""
NetworkManager - 网络环境核心编排器

按顺序初始化所有网络子模块: proxy → mirror → token

代理策略:
  1. 如果配置了 mihomo（proxy/secrets.yaml 有 subscription_url，
     或 my-comfyui-backup/mihomo/ 有手动上传的配置）→ 启动 mihomo
  2. 否则 fallback 到 AutoDL 学术加速（/etc/network_turbo）
  3. 都没有 → 无代理模式

配置持久化:
  mihomo 配置通过 my-comfyui-backup/mihomo/ 目录持久化到 Git 仓库，
  实现跨实例漫游。init 时从 backup 复制到 /etc/mihomo/，
  sync 时把运行时变更同步回 backup。
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

logger = logging.getLogger("autodl_setup")

# 配置文件路径
_PROXY_DIR = Path(__file__).resolve().parent / "proxy"
_PROXY_MANIFEST = _PROXY_DIR / "manifest.yaml"
_PROXY_SECRETS = _PROXY_DIR / "secrets.yaml"

# 持久化目录（相对于 project_root）
_BACKUP_DIR_NAME = "my-comfyui-backup"
_BACKUP_MIHOMO_DIR = "mihomo"

# 需要在 backup ↔ /etc/mihomo 之间同步的文件
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


def _get_project_root() -> Path:
    """获取项目根目录（与 main.py 保持一致）"""
    return Path(__file__).resolve().parent.parent.parent.parent


def _get_backup_mihomo_dir() -> Path:
    """获取 mihomo 持久化备份目录"""
    return _get_project_root() / _BACKUP_DIR_NAME / _BACKUP_MIHOMO_DIR


def _build_proxy_config() -> Optional[ProxyConfig]:
    """从 manifest.yaml + secrets.yaml 构建 ProxyConfig

    判断是否启用 mihomo 的条件（满足任一即可）:
    1. secrets.yaml 中配置了 subscription_url（在线订阅模式）
    2. backup 目录中存在 config.yaml（手动上传模式）

    Returns:
        ProxyConfig 实例，如果两个条件都不满足则返回 None
    """
    secrets = _load_yaml(_PROXY_SECRETS)
    subscription_url = secrets.get("subscription_url", "")

    # 检查 backup 目录是否有手动上传的配置
    backup_config = _get_backup_mihomo_dir() / "config.yaml"
    has_backup = backup_config.exists() and backup_config.stat().st_size > 100

    if not subscription_url and not has_backup:
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

    def _restore_from_backup(self, config: ProxyConfig) -> bool:
        """从 backup 目录恢复 mihomo 配置到运行时目录

        Args:
            config: 代理配置

        Returns:
            True 表示成功恢复了配置
        """
        backup_dir = _get_backup_mihomo_dir()
        backup_config = backup_dir / "config.yaml"

        if not backup_config.exists() or backup_config.stat().st_size < 100:
            return False

        config.config_dir.mkdir(parents=True, exist_ok=True)

        # 复制所有同步文件
        restored = []
        for filename in _SYNC_FILES:
            src = backup_dir / filename
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

    def _backup_config(self, config: ProxyConfig) -> None:
        """将运行时配置备份到 backup 目录

        Args:
            config: 代理配置
        """
        backup_dir = _get_backup_mihomo_dir()
        runtime_config = config.config_dir / "config.yaml"

        if not runtime_config.exists() or runtime_config.stat().st_size < 100:
            return

        backup_dir.mkdir(parents=True, exist_ok=True)

        for filename in _SYNC_FILES:
            src = config.config_dir / filename
            if src.exists() and src.stat().st_size > 0:
                dst = backup_dir / filename
                shutil.copy2(src, dst)

        logger.debug(f"  -> 配置已备份到: {backup_dir}")

    def _setup_proxy(self, verbose: bool) -> None:
        """代理初始化

        策略:
          1. 有 mihomo 配置 → 先用 turbo 引导下载，再切到 mihomo
          2. 没有 mihomo 配置 → 直接用 turbo 兜底

        配置来源优先级:
          1. backup 目录已有配置（手动上传 / 上次持久化）→ 恢复到运行时目录
          2. subscription_url 在线下载 → 下载后备份到 backup 目录
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

        # 从 backup 恢复配置到 /etc/mihomo/
        self._restore_from_backup(config)

        # 下载/更新订阅（如果 backup 已有配置且无 subscription_url，会直接复用）
        if not backend.update_subscription():
            if verbose:
                logger.warning("  -> [WARN] 订阅更新失败，回退到 AutoDL 学术加速")
            load_autodl_turbo(verbose)
            return

        # 启动成功前的配置已经就绪，备份一份到 backup
        self._backup_config(config)

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

    def sync_config(self) -> None:
        """将运行时 mihomo 配置同步回 backup 目录

        应在 main.py 的 sync 动作中调用，把节点选择（cache.db）
        等运行时变更持久化到 my-comfyui-backup/mihomo/，
        随 userdata 的 git push 一起推送到远程仓库。
        """
        config = _build_proxy_config()
        if config is None:
            return

        backup_dir = _get_backup_mihomo_dir()
        runtime_config = config.config_dir / "config.yaml"

        if not runtime_config.exists():
            return

        backup_dir.mkdir(parents=True, exist_ok=True)

        synced = []
        for filename in _SYNC_FILES:
            src = config.config_dir / filename
            if src.exists() and src.stat().st_size > 0:
                dst = backup_dir / filename
                # 只在内容变化时复制（避免无意义的 git diff）
                if dst.exists() and dst.read_bytes() == src.read_bytes():
                    continue
                shutil.copy2(src, dst)
                synced.append(filename)

        if synced:
            logger.info(f"  -> mihomo 配置已同步到持久化目录: {', '.join(synced)}")
        else:
            logger.debug(f"  -> mihomo 配置无变更，跳过同步")


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


def sync_proxy_config() -> None:
    """同步 mihomo 配置到持久化目录 (全局入口，供 sync 阶段调用)"""
    get_network_manager().sync_config()


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
