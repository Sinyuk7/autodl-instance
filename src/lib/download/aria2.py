"""
Aria2 多线程下载策略

适用于 CivitAI、直链以及 HuggingFace 的非 Hub 场景
"""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.schema import EnvKey

ENV_CIVITAI_TOKEN = EnvKey.CIVITAI_API_TOKEN
ENV_HF_TOKEN = EnvKey.HF_TOKEN
from src.lib.download.base import CacheEntry, DownloadStrategy, PurgeResult

logger = logging.getLogger("autodl_setup")

# Aria2 下载临时文件目录
_ARIA2_TMP_DIR = Path("/tmp") / "aria2"


def _calc_dir_size(path: Path) -> int:
    """递归计算目录大小（字节），路径不存在返回 0"""
    if not path.exists():
        return 0
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


class Aria2Strategy(DownloadStrategy):
    """Aria2 多线程下载策略
    
    配置段 (download.yaml → download.aria2):
        connections:    每服务器最大连接数（默认 32）
        split_size:     分片大小 MB（默认 5）
        max_retries:    最大重试次数（默认 5）
        timeout:        超时秒数（默认 30）
        disk_cache:     磁盘缓存 MB（默认 64）
        file_allocation: 文件预分配方式（默认 none）
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        self._connections     = cfg.get("connections", 32)
        self._split_size      = cfg.get("split_size", 5)
        self._max_retries     = cfg.get("max_retries", 5)
        self._timeout         = cfg.get("timeout", 30)
        self._disk_cache      = cfg.get("disk_cache", 64)
        self._file_allocation = cfg.get("file_allocation", "none")

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
            "--max-connection-per-server", str(self._connections),
            "--split",                     str(self._connections),
            "--min-split-size",            f"{self._split_size}M",
            "--max-tries",                 str(self._max_retries),
            "--timeout",                   str(self._timeout),
            "--connect-timeout",           "10",
            "--retry-wait",                "3",
            "--disk-cache",                f"{self._disk_cache}M",
            "--file-allocation",           self._file_allocation,
            "--continue=true",
            "--auto-file-renaming=false",
            "--allow-overwrite=true",
            "--console-log-level=notice",
            "--summary-interval=5",
            "--optimize-concurrent-downloads=true",
            "--stream-piece-selector=geom",
            "--dir", str(target_path.parent),
            "--out", target_path.name,
        ]

        # CivitAI Token
        if "civitai.com" in url:
            token = os.environ.get(ENV_CIVITAI_TOKEN)
            if token:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}token={token}"

        # HuggingFace Token（aria2 作为 fallback 时）
        if "huggingface.co" in url:
            hf_token = os.environ.get(ENV_HF_TOKEN)
            if hf_token:
                cmd += ["--header", f"Authorization: Bearer {hf_token}"]

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

    def cache_info(self) -> List[CacheEntry]:
        """返回 aria2 临时目录的缓存条目"""
        return [
            CacheEntry(
                name="Aria2 临时文件",
                path=_ARIA2_TMP_DIR,
                size_bytes=_calc_dir_size(_ARIA2_TMP_DIR),
                exists=_ARIA2_TMP_DIR.exists(),
            )
        ]

    def purge_cache(self, pattern: Optional[str] = None) -> List[PurgeResult]:
        """清理 aria2 临时目录（不支持 pattern，全量清理）"""
        if not _ARIA2_TMP_DIR.exists():
            return []
        size = _calc_dir_size(_ARIA2_TMP_DIR)
        try:
            shutil.rmtree(_ARIA2_TMP_DIR)
            return [PurgeResult(str(_ARIA2_TMP_DIR), size, True)]
        except OSError as e:
            return [PurgeResult(str(_ARIA2_TMP_DIR), 0, False, str(e))]

