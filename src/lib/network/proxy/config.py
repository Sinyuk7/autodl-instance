"""
mihomo 订阅配置管理

职责:
- 下载 Clash 订阅配置
- 修补配置 (覆盖端口、清理冲突项、安全加固)
"""
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from src.lib.network.proxy.base import ProxyConfig

logger = logging.getLogger("autodl_setup")


def download_subscription(config: ProxyConfig, config_file: Path) -> bool:
    """下载/更新 Clash 订阅配置

    Args:
        config: 代理配置
        config_file: 配置文件写入路径

    Returns:
        True 表示配置更新成功
    """
    url = config.subscription_url
    if not url:
        logger.error("  -> ✗ 未配置订阅地址 (subscription_url)")
        return False

    logger.info("  -> 正在更新订阅配置...")

    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 使用 mihomo 兼容的 UA，部分机场会据此返回支持更多协议的配置
        # (如 vless, hysteria2 等 mihomo 专有协议)
        req = urllib.request.Request(url, headers={
            "User-Agent": f"clash.meta/{config.version}",
        })

        with urllib.request.urlopen(req, timeout=30) as resp:
            config_data = resp.read()

        # 写入配置文件
        config_file.write_bytes(config_data)

        # 注入/覆盖本地端口和 API 配置
        patch_config(config, config_file)

        logger.info(f"  -> ✓ 订阅配置已更新: {config_file}")
        return True

    except Exception as e:
        logger.error(f"  -> ✗ 订阅更新失败: {e}")
        return False


def patch_config(config: ProxyConfig, config_file: Path) -> None:
    """修补订阅配置，覆盖端口和 API 设置

    订阅下载的 YAML 可能有自己的端口设定，我们需要确保使用
    manifest.yaml 中指定的端口。同时清理可能冲突的配置项。

    修补项:
    1. 清理旧式端口 (port, socks-port, redir-port, tproxy-port)
    2. 设置 mixed-port, external-controller, mode 等核心配置
    3. 关闭 IPv6 和进程匹配 (容器/实例环境)
    4. 持久化节点选择
    5. 确保 TUN 模式关闭 (需要特殊权限)
    6. DNS 安全配置 (避免绑定 0.0.0.0:53)
    7. API 认证设置

    Args:
        config: 代理配置
        config_file: 配置文件路径
    """
    import yaml

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # ── 1. 清理旧式端口配置，避免与 mixed-port 冲突 ──
        for key in ("port", "socks-port", "redir-port", "tproxy-port"):
            data.pop(key, None)

        # ── 2. 覆盖核心配置 ──
        data["mixed-port"] = config.proxy_port
        data["external-controller"] = f"127.0.0.1:{config.api_port}"
        data["allow-lan"] = False
        data["mode"] = "rule"
        data["log-level"] = "warning"

        # ── 3. 环境适配 ──
        # 容器/实例中关闭 IPv6 和进程匹配
        data["ipv6"] = False
        data["find-process-mode"] = "off"

        # ── 4. 持久化节点选择 ──
        data.setdefault("profile", {})
        data["profile"]["store-selected"] = True
        data["profile"]["store-fake-ip"] = True

        # ── 5. 确保 TUN 模式关闭 ──
        if "tun" in data and isinstance(data["tun"], dict):
            data["tun"]["enable"] = False

        # ── 6. DNS 安全配置 ──
        if "dns" in data and isinstance(data["dns"], dict):
            dns_listen = str(data["dns"].get("listen", ""))
            # 避免绑定 0.0.0.0:53 (需要 root 且与系统 DNS 冲突)
            if dns_listen and ":53" in dns_listen and "1053" not in dns_listen:
                data["dns"]["listen"] = "127.0.0.1:1053"

        # ── 7. API 认证 ──
        if config.api_secret:
            data["secret"] = config.api_secret

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    except Exception as e:
        logger.warning(f"  -> [WARN] 配置修补失败 (仍可使用原始配置): {e}")
