"""
mihomo 订阅配置管理

职责:
- 下载 Clash 订阅配置
- 修补配置 (覆盖端口、清理冲突项、安全加固)
- 预下载 GeoIP/GeoSite 数据库 (避免 mihomo 启动时因网络问题下载失败)
"""
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from src.lib.network.proxy.base import ProxyConfig

logger = logging.getLogger("autodl_setup")


class _RedirectHandlerKeepUA(urllib.request.HTTPRedirectHandler):
    """跟随重定向时保留 User-Agent 头

    Python 标准库的 HTTPRedirectHandler 在 302 重定向后会丢弃
    自定义 headers（包括 User-Agent），导致重定向后的请求使用
    Python-urllib 默认 UA，被机场后端拒绝 (403)。

    此 handler 确保重定向后的请求保留原始 User-Agent。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            # 保留原始请求的 User-Agent
            ua = req.get_header("User-agent")  # urllib 内部用首字母大写
            if ua:
                new_req.add_unredirected_header("User-Agent", ua)
        return new_req


# 订阅下载使用的 User-Agent 列表（按优先级排列）
# 部分机场会根据 UA 返回不同格式的配置，或拒绝不认识的 UA
_SUBSCRIPTION_USER_AGENTS = [
    "clash.meta",                                    # mihomo 官方 UA（最优，支持 vless/hysteria2）
    "ClashForAndroid/2.5.12",                        # CFA 常见 UA
    "clash-verge/v1.3.8",                            # clash-verge 客户端
    "ClashX/1.95.1",                                 # ClashX macOS 客户端
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",    # 通用浏览器 UA（兜底）
]


def download_subscription(config: ProxyConfig, config_file: Path) -> bool:
    """下载/更新 Clash 订阅配置

    支持:
    - 多 User-Agent 重试 (部分机场会拒绝特定 UA)
    - 通过系统代理下载 (如 AutoDL turbo 学术加速)
    - 已有配置文件时下载失败不覆盖

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

    # 构建两个 opener:
    #   1. 直连（机场订阅通常是国内地址，直连更快更可靠）
    #   2. 通过环境代理（turbo 学术加速，作为兜底）
    # 使用自定义 redirect handler 保留 UA，防止重定向后被机场 403
    redirect_handler = _RedirectHandlerKeepUA()
    direct_opener = urllib.request.build_opener(
        redirect_handler,
        urllib.request.ProxyHandler({})  # 空字典 = 不使用任何代理
    )
    proxy_opener = urllib.request.build_opener(
        redirect_handler,
        urllib.request.ProxyHandler()    # 无参数 = 使用环境变量中的代理
    )

    last_error = None
    for ua in _SUBSCRIPTION_USER_AGENTS:
        for opener, label in [(direct_opener, "直连"), (proxy_opener, "代理")]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": ua})
                with opener.open(req, timeout=30) as resp:
                    config_data = resp.read()

                # 基本验证：订阅内容不能太短（至少应该是一个有效 YAML）
                if len(config_data) < 100:
                    logger.debug(f"  -> [{label}] UA '{ua}' 返回数据过短 ({len(config_data)} bytes)，跳过")
                    continue

                # 写入配置文件
                config_file.write_bytes(config_data)

                # 注入/覆盖本地端口和 API 配置
                patch_config(config, config_file)

                logger.info(f"  -> ✓ 订阅配置已更新 ({label}): {config_file}")
                return True

            except Exception as e:
                last_error = e
                logger.debug(f"  -> [{label}] UA '{ua}' 下载失败: {e}")
                continue

    # 所有组合都失败了
    logger.error(f"  -> ✗ 订阅更新失败 (已尝试 {len(_SUBSCRIPTION_USER_AGENTS)} 种 UA × 2 种网络): {last_error}")

    # 如果已有旧配置，提示可以继续使用
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
