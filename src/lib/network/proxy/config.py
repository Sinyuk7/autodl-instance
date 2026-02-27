"""
mihomo 订阅配置管理

职责:
- 下载 Clash 订阅配置
- 修补配置 (覆盖端口、清理冲突项、安全加固)
- 预下载 GeoIP/GeoSite 数据库 (避免 mihomo 启动时因网络问题下载失败)
"""
import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

from src.lib.network.proxy.base import ProxyConfig

logger = logging.getLogger("autodl_setup")

# mihomo 官方 UA（部分机场据此返回支持 vless/hysteria2 等协议的配置）
_DEFAULT_UA = "clash.meta"


def _download_with_curl(url: str, dest: Path, ua: str = _DEFAULT_UA) -> bool:
    """使用 curl 下载订阅配置

    很多机场后端（如 V2Board）经过 Cloudflare 保护，会检测 TLS 指纹、
    Cookie、HTTP/2 等特征。Python urllib 的 TLS 指纹与主流浏览器/客户端
    差异较大，容易被 403。curl 的 TLS 栈更接近主流客户端，兼容性更好。

    Args:
        url: 订阅地址
        dest: 下载目标路径
        ua: User-Agent

    Returns:
        True 表示下载成功
    """
    if not shutil.which("curl"):
        logger.debug("  -> curl 不可用，跳过")
        return False

    try:
        result = subprocess.run(
            [
                "curl", "-sSL",          # silent, show errors, follow redirects
                "--max-time", "30",      # 超时 30 秒
                "--retry", "2",          # 重试 2 次
                "--retry-delay", "3",    # 重试间隔 3 秒
                "-H", f"User-Agent: {ua}",
                "-o", str(dest),
                url,
            ],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            logger.debug(f"  -> curl 下载失败 (code={result.returncode}): {result.stderr.strip()}")
            dest.unlink(missing_ok=True)
            return False

        # 验证下载内容
        if not dest.exists() or dest.stat().st_size < 100:
            logger.debug(f"  -> curl 下载的文件过小或不存在")
            dest.unlink(missing_ok=True)
            return False

        return True

    except Exception as e:
        logger.debug(f"  -> curl 异常: {e}")
        dest.unlink(missing_ok=True)
        return False


def download_subscription(config: ProxyConfig, config_file: Path) -> bool:
    """下载/更新 Clash 订阅配置

    下载策略 (按优先级):
    1. curl 直连 — TLS 指纹兼容性最好，绕过 Cloudflare 检测
    2. curl 通过 noproxy — 明确不走系统代理
    3. 如果有旧配置 — 复用旧配置继续

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
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # 策略 1: curl 下载（TLS 指纹兼容性好，能绕过 Cloudflare 等 WAF）
    if _download_with_curl(url, config_file, ua=_DEFAULT_UA):
        patch_config(config, config_file)
        logger.info(f"  -> ✓ 订阅配置已更新: {config_file}")
        return True

    logger.debug("  -> curl 默认 UA 失败，尝试 ClashForAndroid UA...")

    # 策略 2: 换一个 UA 重试
    if _download_with_curl(url, config_file, ua="ClashForAndroid/2.5.12"):
        patch_config(config, config_file)
        logger.info(f"  -> ✓ 订阅配置已更新: {config_file}")
        return True

    # 所有策略都失败了
    logger.error(f"  -> ✗ 订阅更新失败")

    # 如果已有旧配置，复用继续
    if config_file.exists() and config_file.stat().st_size > 0:
        logger.info("  -> 检测到已有订阅配置，将使用旧配置继续")
        patch_config(config, config_file)
        return True

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
    8. GeoIP/GeoSite 数据库配置 (使用国内镜像 + 预下载)

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

        # ── 8. GeoIP/GeoSite 数据库配置 ──
        # 使用国内可达的 CDN 镜像，避免 mihomo 从 GitHub 下载超时
        # 同时关闭自动更新（由我们预下载管理）
        data["geodata-mode"] = True
        data["geo-auto-update"] = False
        data["geo-update-interval"] = 168  # 7 天
        data["geox-url"] = {
            "geoip": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
            "geosite": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
            "mmdb": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/country.mmdb",
            "asn": "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/GeoLite2-ASN.mmdb",
        }

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        # 预下载 GeoIP 数据库，避免 mihomo 启动时下载失败
        _ensure_geodata(config.config_dir)

    except Exception as e:
        logger.warning(f"  -> [WARN] 配置修补失败 (仍可使用原始配置): {e}")


# ── GeoIP / GeoSite 数据库预下载 ───────────────────────────

# 国内 CDN 镜像，按优先级排列
_GEO_MIRRORS = [
    "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release",
    "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release",
    "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release",
]

# 需要预下载的文件列表
_GEO_FILES = [
    ("country.mmdb", "country.mmdb"),      # GeoIP MMDB (GEOIP 规则必需)
    ("geoip.dat", "geoip.dat"),            # GeoIP DAT (geodata-mode 使用)
    ("geosite.dat", "geosite.dat"),        # GeoSite DAT (GEOSITE 规则使用)
]


def _ensure_geodata(config_dir: Path) -> None:
    """预下载 GeoIP/GeoSite 数据库到 config_dir

    mihomo 启动时如果找不到这些文件会尝试从 GitHub 下载，
    在 AutoDL 等受限网络环境中几乎一定会超时。
    预先下载可以避免这个问题。

    Args:
        config_dir: mihomo 配置目录 (如 /etc/mihomo)
    """
    config_dir.mkdir(parents=True, exist_ok=True)

    for filename, _ in _GEO_FILES:
        target = config_dir / filename
        if target.exists() and target.stat().st_size > 0:
            continue  # 已存在且非空，跳过

        logger.info(f"  -> 正在下载 {filename}...")

        downloaded = False
        for mirror in _GEO_MIRRORS:
            url = f"{mirror}/{filename}"
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "mihomo/geodata-downloader",
                })
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()

                if len(data) < 1024:
                    # 文件太小，可能是错误页面
                    logger.warning(f"     {filename} 从 {mirror} 下载的文件过小，尝试下一个镜像")
                    continue

                target.write_bytes(data)
                logger.info(f"     ✓ {filename} ({len(data) // 1024} KB)")
                downloaded = True
                break

            except Exception as e:
                logger.warning(f"     {filename} 从 {mirror} 下载失败: {e}")
                continue

        if not downloaded:
            logger.warning(
                f"  -> [WARN] {filename} 所有镜像均下载失败，"
                f"mihomo 启动时可能会报错"
            )
