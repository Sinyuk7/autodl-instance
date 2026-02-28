"""
Aria2 多线程下载策略

适用于 CivitAI、直链以及 HuggingFace 的非 Hub 场景

文件管理说明 (基于 aria2 官方文档):
- .aria2 控制文件: 与下载文件同目录，用于断点续传，下载完成后自动删除
- --disk-cache: 是内存缓存，不产生磁盘文件
- dht.dat: DHT 路由表，仅 BT 下载使用，我们不涉及
- session 文件: 需要 --save-session 才会产生，我们不使用
"""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from src.core.schema import EnvKey

ENV_CIVITAI_TOKEN = EnvKey.CIVITAI_API_TOKEN
ENV_HF_TOKEN = EnvKey.HF_TOKEN
from src.lib.download.base import CacheEntry, DownloadStrategy, PurgeResult

logger = logging.getLogger("autodl_setup")


class Aria2Strategy(DownloadStrategy):
    """Aria2 多线程下载策略
    
    配置段 (manifest.yaml → aria2):
        connections:        每服务器最大连接数（默认 16，aria2 上限）
        split_size:         最小分片大小 MB（默认 5）
        max_retries:        最大重试次数（默认 5）
        timeout:            传输超时秒数（默认 30）
        connect_timeout:    连接超时秒数（默认 10）
        retry_wait:         重试等待秒数（默认 3）
        disk_cache:         磁盘缓存 MB（默认 64）
        file_allocation:    文件预分配方式（默认 none）
        lowest_speed_limit: 最低速度限制（默认 1K）
        max_file_not_found: 文件找不到最大重试次数（默认 2）
        uri_selector:       URI 选择算法（默认 adaptive）
        piece_length:       分片长度（默认 1M）
    
    文档: https://aria2.github.io/manual/en/html/aria2c.html
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        # 连接与分片
        self._connections     = min(cfg.get("connections", 16), 16)  # aria2 上限 16
        self._split_size      = cfg.get("split_size", 5)
        self._piece_length    = cfg.get("piece_length", "1M")
        # 重试与超时
        self._max_retries     = cfg.get("max_retries", 5)
        self._timeout         = cfg.get("timeout", 30)
        self._connect_timeout = cfg.get("connect_timeout", 10)
        self._retry_wait      = cfg.get("retry_wait", 3)
        self._max_file_not_found = cfg.get("max_file_not_found", 2)
        # 速度限制
        self._lowest_speed_limit = cfg.get("lowest_speed_limit", "1K")
        # 磁盘与缓存
        self._disk_cache      = cfg.get("disk_cache", 64)
        self._file_allocation = cfg.get("file_allocation", "none")
        # URI 选择
        self._uri_selector    = cfg.get("uri_selector", "adaptive")

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """读取 download/manifest.yaml 中 aria2 段配置"""
        try:
            import yaml
            config_path = Path(__file__).parent / "manifest.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    raw: Dict[str, Any] = yaml.safe_load(f) or {}
                    return raw.get("aria2", {})
        except Exception:
            pass
        return {}

    # ── 元信息 ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "aria2"

    # ── 可用性 ──────────────────────────────────────────────

    def is_available(self) -> bool:
        return shutil.which("aria2c") is not None

    def ensure_available(self) -> bool:
        if self.is_available():
            return True
        return self._install_aria2()

    def _install_aria2(self) -> bool:
        if sys.platform != "linux":
            return False
        logger.info("  -> [aria2] 正在安装多线程下载器...")
        try:
            subprocess.run(["apt-get", "update", "-qq"], check=False, capture_output=True)
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "aria2"],
                check=True, capture_output=True, text=True,
            )
            logger.info("  -> [aria2] 安装完成。")
            return True
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.strip() if e.stderr else "未知错误"
            logger.warning(f"  -> [aria2] 安装失败: {stderr_msg}")
            return False
        except FileNotFoundError:
            logger.warning("  -> [aria2] apt-get 不可用，跳过安装。")
            return False

    # ── 下载生命周期 ─────────────────────────────────────────

    def pre_download(self, target_path: Path) -> None:
        """确保目标目录存在"""
        target_path.parent.mkdir(parents=True, exist_ok=True)

    def post_download(self, target_path: Path) -> None:
        """清理 aria2 产生的 .aria2 控制文件"""
        aria2_ctrl = Path(str(target_path) + ".aria2")
        if aria2_ctrl.exists():
            try:
                aria2_ctrl.unlink()
                logger.debug(f"  -> [aria2] 已清理控制文件: {aria2_ctrl.name}")
            except OSError as e:
                logger.debug(f"  -> [aria2] 清理控制文件失败: {e}")

    def on_interrupt(self, target_path: Path) -> None:
        """用户中断时保留 .aria2 控制文件（支持断点续传）"""
        pass  # aria2 自身支持断点续传，中断时无需清理

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
    def _is_huggingface_url(url: str, hf_endpoint: str) -> bool:
        """判断 URL 是否为 HuggingFace 或其镜像站
        
        Args:
            url: 待检查的 URL
            hf_endpoint: HF_ENDPOINT 环境变量值（镜像站地址）
            
        Returns:
            True 如果 URL 属于 HuggingFace 或其镜像站
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        
        # 原始 HuggingFace 域名
        if host == "huggingface.co" or host.endswith(".huggingface.co"):
            return True
        
        # 镜像站域名
        if hf_endpoint:
            mirror_parsed = urlparse(hf_endpoint)
            mirror_host = (mirror_parsed.hostname or "").lower()
            if mirror_host and (host == mirror_host or host.endswith(f".{mirror_host}")):
                return True
        
        return False

    def _log_proxy_settings(self) -> None:
        """记录当前代理设置（用于调试）"""
        proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
        no_proxy = os.environ.get("no_proxy") or os.environ.get("NO_PROXY")
        
        if proxy:
            logger.info(f"  -> [aria2] 代理: {proxy}")
            if no_proxy:
                logger.debug(f"  -> [aria2] 不代理: {no_proxy}")
        else:
            logger.debug("  -> [aria2] 未配置代理")

    # ── 核心下载 ────────────────────────────────────────────

    def download(self, url: str, target_path: Path, dry_run: bool = False) -> bool:
        """使用 aria2c 多线程下载
        
        dry_run=True 时仅检查 aria2c 可用性，不实际下载。
        """
        if dry_run:
            available = self.is_available()
            logger.info(f"  -> [aria2] [dry-run] aria2c {'可用' if available else '不可用'}")
            return available

        # 生命周期由 Manager 统一编排，这里只做纯下载
        cmd: list[str] = [
            "aria2c",
            # === 连接与分片 ===
            "--max-connection-per-server", str(self._connections),
            "--split",                     str(self._connections),
            "--min-split-size",            f"{self._split_size}M",
            "--piece-length",              self._piece_length,
            # === 重试与超时 ===
            "--max-tries",                 str(self._max_retries),
            "--timeout",                   str(self._timeout),
            "--connect-timeout",           str(self._connect_timeout),
            "--retry-wait",                str(self._retry_wait),
            "--max-file-not-found",        str(self._max_file_not_found),
            # === 速度限制 ===
            "--lowest-speed-limit",        self._lowest_speed_limit,
            # === 磁盘与缓存 ===
            "--disk-cache",                f"{self._disk_cache}M",
            "--file-allocation",           self._file_allocation,
            # === 断点续传与覆盖 ===
            "--continue=true",
            "--auto-file-renaming=false",
            "--allow-overwrite=true",
            # === 日志与输出（保持静默） ===
            "--console-log-level=warn",
            "--summary-interval=0",
            "--download-result=hide",
            # === 性能优化 ===
            "--optimize-concurrent-downloads=true",
            "--stream-piece-selector=geom",
            "--uri-selector",              self._uri_selector,
            "--async-dns=true",
            "--enable-http-keep-alive=true",
            "--http-accept-gzip=true",
            # === 目标路径 ===
            "--dir", str(target_path.parent),
            "--out", target_path.name,
        ]

        # 记录代理设置
        self._log_proxy_settings()

        # CivitAI: 不在 aria2 层面处理 token
        # Token 认证已在 civitai.py 的 API 调用中完成，aria2 直接使用返回的下载 URL
        # 注意: 某些需要登录的模型可能需要额外处理，但大部分公开模型无需 token

        # HuggingFace: 替换为镜像站 + 注入 Token
        hf_endpoint = os.environ.get("HF_ENDPOINT", "")
        if "huggingface.co" in url and hf_endpoint and "huggingface.co" not in hf_endpoint:
            url = url.replace("https://huggingface.co", hf_endpoint)
            logger.info(f"  -> [aria2] 使用镜像站: {hf_endpoint}")
        
        # 使用精确的域名匹配判断是否需要注入 HF Token
        if self._is_huggingface_url(url, hf_endpoint):
            hf_token = os.environ.get(ENV_HF_TOKEN)
            if hf_token:
                cmd += ["--header", f"Authorization: Bearer {hf_token}"]
            else:
                logger.debug("  -> [aria2] HuggingFace Token 未配置，部分模型可能无法下载")

        cmd.append(url)

        logger.info(f"  -> [aria2] 启动 {self._connections} 线程下载...")

        try:
            process = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
            process.wait()
            return process.returncode == 0 and target_path.exists()
        except FileNotFoundError:
            logger.error("  -> [ERROR] aria2c 未安装，请运行: apt install aria2")
            return False
        except Exception as e:
            logger.error(f"  -> [ERROR] aria2 下载失败: {e}")
            return False

    # ── 缓存管理 ─────────────────────────────────────────────
    #
    # aria2 不产生持久化缓存目录:
    # - --disk-cache 是内存缓存，进程结束即释放
    # - .aria2 控制文件与下载文件同目录，用于断点续传，下载完成后自动删除
    #
    # 因此 cache_info() 和 purge_cache() 均返回空，
    # 保留接口以便未来添加其他有缓存的策略（如 HuggingFace Hub）

    def cache_info(self) -> List[CacheEntry]:
        """aria2 无持久化缓存目录，返回空列表"""
        return []

    def purge_cache(self) -> List[PurgeResult]:
        """aria2 无持久化缓存，返回空列表"""
        return []

