"""
HuggingFace Hub 下载策略

使用官方 huggingface_hub 库下载，自动利用 hf_xet 加速
（huggingface_hub >= 0.32.0 自动安装 hf_xet，hf_transfer 已 deprecated）

特性:
  - 版本感知缓存，断点续传
  - hf_xet chunk-based 去重加速（自动启用）
  - 下载前清理死锁文件
  - post_download 清理 local_dir 元数据目录
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.schema import EnvKey

ENV_HF_TOKEN = EnvKey.HF_TOKEN
from src.core.utils import logger
from src.lib.download.base import CacheEntry, DownloadStrategy, PurgeResult
from src.lib.download.url_utils import parse_hf_url


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


class HuggingFaceHubStrategy(DownloadStrategy):
    """HuggingFace Hub 官方下载策略
    
    配置段 (download.yaml → download.hf_hub):
        enabled:                是否启用（默认 True）
        xet_high_performance:   开启 Xet 高性能模式（默认 True）
        xet_chunk_cache_mb:     Xet Chunk Cache 大小 MB（默认 0，禁用）
        xet_write_sequentially: 是否为机械硬盘优化（默认 False）
        etag_timeout:           ETag 检查超时秒数（默认 10）
        xet_concurrent_gets:    Xet 并发获取数（默认 16）
    """

    # HF Hub 缓存根目录
    _HF_HUB_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
    _HF_DL_CACHE  = Path.home() / ".cache" / "huggingface" / "download"
    # Xet 缓存目录 (chunk_cache, shard_cache, staging)
    _HF_XET_CACHE = Path.home() / ".cache" / "huggingface" / "xet"

    def __init__(self) -> None:
        cfg = self._load_config()
        self._enabled = cfg.get("enabled", True)
        self._xet_high_performance = cfg.get("xet_high_performance", True)
        self._xet_chunk_cache_mb = cfg.get("xet_chunk_cache_mb", 0)
        self._xet_write_sequentially = cfg.get("xet_write_sequentially", False)
        self._etag_timeout = cfg.get("etag_timeout", 10)
        self._xet_concurrent_gets = cfg.get("xet_concurrent_gets", 16)
        
        # 记录当前下载的 filename，供 cleanup 使用
        self._current_filename: Optional[str] = None

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """读取 download/manifest.yaml 中 hf_hub 段配置"""
        try:
            import yaml
            config_path = Path(__file__).parent / "manifest.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    raw: Dict[str, Any] = yaml.safe_load(f) or {}
                    return raw.get("hf_hub", {})
        except Exception as e:
            logger.debug(f"  -> [hf_hub] 加载配置失败，使用默认值: {e}")
        return {}

    # ── 元信息 ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "hf_hub"

    # ── 可用性 ──────────────────────────────────────────────

    def is_available(self) -> bool:
        if not self._enabled:
            return False
        try:
            import huggingface_hub  # type: ignore[import-untyped]  # noqa: F401
            return True
        except ImportError:
            return False

    def ensure_available(self) -> bool:
        """确保 huggingface_hub 可用，并尝试升级以获得 hf_xet 加速"""
        if not self._enabled:
            return False
            
        try:
            import huggingface_hub  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            logger.error("  -> [hf_hub] huggingface_hub 未安装，请先安装。")
            return False
            
        self._ensure_hf_xet()
        return True

    def _ensure_hf_xet(self) -> None:
        """确保 hf_xet 已安装（huggingface_hub >= 0.32.0 会自动携带）"""
        try:
            import hf_xet  # type: ignore[import-not-found]  # noqa: F401
            return  # 已安装，无需处理
        except ImportError:
            pass

        uv_bin = shutil.which("uv")
        installer = [uv_bin, "pip", "install", "--system"] if uv_bin else ["pip", "install"]
        logger.info("  -> [hf_hub] 正在升级 huggingface_hub 以获取 hf_xet 加速模块...")
        try:
            subprocess.run(
                installer + ['-U', 'huggingface_hub'],
                check=True,
                capture_output=True,
            )
            logger.info("  -> [hf_hub] huggingface_hub 升级完成，hf_xet 加速已就绪。")
        except subprocess.CalledProcessError as e:
            logger.warning(f"  -> [hf_hub] huggingface_hub 升级失败，将使用标准传输: {e}")

    # ── 下载生命周期 ─────────────────────────────────────────

    def _inject_env_vars(self) -> None:
        """注入 HF Hub 和 Xet 相关环境变量"""
        # 1. 注入 HF Hub 环境变量
        if self._etag_timeout:
            os.environ["HF_HUB_ETAG_TIMEOUT"] = str(self._etag_timeout)
        
        # 2. 注入 Xet 环境变量
        if self._xet_high_performance:
            os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
        if self._xet_chunk_cache_mb > 0:
            os.environ["HF_XET_CHUNK_CACHE_SIZE_BYTES"] = str(self._xet_chunk_cache_mb * 1024 * 1024)
        if self._xet_write_sequentially:
            os.environ["HF_XET_RECONSTRUCT_WRITE_SEQUENTIALLY"] = "1"
        if self._xet_concurrent_gets and self._xet_concurrent_gets != 16:
            os.environ["HF_XET_NUM_CONCURRENT_RANGE_GETS"] = str(self._xet_concurrent_gets)

    def pre_download(self, target_path: Path) -> None:
        """下载前准备：注入环境变量，清理死锁文件"""
        self._inject_env_vars()
            
        # 清理 HF 死锁文件
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_hf_locks(target_path.parent)

    def post_download(self, target_path: Path) -> None:
        """清理 local_dir 下 hf_hub_download 产生的 .cache/huggingface 元数据目录"""
        local_cache = target_path.parent / ".cache" / "huggingface"
        if local_cache.exists():
            try:
                shutil.rmtree(local_cache)
                logger.debug(f"  -> [hf_hub] 已清理元数据目录: {local_cache}")
            except OSError as e:
                logger.debug(f"  -> [hf_hub] 清理元数据目录失败: {e}")

        # 清理因 filename 含子路径产生的嵌套空目录
        if self._current_filename:
            self._cleanup_nested_dirs(target_path.parent, self._current_filename)

    def on_interrupt(self, target_path: Path) -> None:
        """用户中断时清理锁文件和嵌套空目录（保留缓存以支持断点续传）"""
        self._clear_hf_locks(target_path.parent)
        if self._current_filename:
            self._cleanup_nested_dirs(target_path.parent, self._current_filename)

    # ── 核心下载 ────────────────────────────────────────────

    def download(self, url: str, target_path: Path, dry_run: bool = False) -> bool:
        """使用 huggingface_hub 下载 HF 文件
        
        dry_run=True 时调用 hf_hub_download(dry_run=True) 预估下载量，不实际写盘。
        
        注意: 当 HF repo 中的 filename 包含子路径（如 split_files/text_encoders/model.safetensors）
        时，hf_hub_download 的 local_dir 模式会在目标目录下创建这些嵌套目录。为避免污染用户
        的模型目录，当 filename 含 "/" 时，先下载到临时目录，再将文件 move 到 target_path。
        """
        import tempfile
        from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]

        parsed = parse_hf_url(url)
        if not parsed:
            logger.error(f"  -> [ERROR] 无法解析 HuggingFace URL: {url}")
            return False

        repo_id, filename, revision, repo_type = parsed
        self._current_filename = filename

        # 判断 filename 是否含子路径（如 split_files/text_encoders/model.safetensors）
        # 若含子路径，使用临时目录作为 local_dir，避免在目标目录下创建嵌套空目录
        has_nested_path = "/" in filename
        if has_nested_path:
            staging_dir = Path(tempfile.mkdtemp(prefix="hf_dl_"))
            local_dir = str(staging_dir)
        else:
            staging_dir = None
            local_dir = str(target_path.parent)

        token = os.environ.get(ENV_HF_TOKEN)

        download_kwargs: Dict[str, Any] = {
            "repo_id":    repo_id,
            "filename":   filename,
            "local_dir":  local_dir,
            "local_dir_use_symlinks": False,
        }
        if revision:
            download_kwargs["revision"] = revision
        if repo_type:
            download_kwargs["repo_type"] = repo_type
        if token:
            download_kwargs["token"] = token

        # ── dry_run 模式 ──────────────────────────────────
        if dry_run:
            self._inject_env_vars()
            try:
                result = hf_hub_download(**download_kwargs, dry_run=True)
                size = getattr(result, "size", None)
                if size == 0:
                    logger.info(f"  -> [hf_hub] [dry-run] {filename} 已缓存，无需下载")
                else:
                    size_mb = (size or 0) / (1024 * 1024)
                    logger.info(f"  -> [hf_hub] [dry-run] {filename} 需下载 {size_mb:.1f} MB")
                return True
            except Exception as e:
                logger.error(f"  -> [ERROR] dry_run 预估失败: {e}")
                return False
            finally:
                if staging_dir and staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)

        # ── 正式下载（生命周期由 Manager 统一编排）─────────
        hf_endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
        is_mirror = "huggingface.co" not in hf_endpoint
        if is_mirror:
            logger.info(f"  -> [hf_hub] 镜像站: {hf_endpoint}")
        else:
            logger.info(f"  -> [hf_hub] 端点: {hf_endpoint} (官方)")
        logger.info(f"  -> [hf_hub] 下载: {repo_id} / {filename}")

        try:
            downloaded_path = Path(hf_hub_download(**download_kwargs))

            # 将文件移到最终目标路径
            if downloaded_path.exists() and downloaded_path.resolve() != target_path.resolve():
                if target_path.exists():
                    target_path.unlink()
                shutil.move(str(downloaded_path), str(target_path))
                logger.debug(f"  -> [hf_hub] 已移动: {downloaded_path.name} → {target_path.name}")

            if target_path.exists():
                size_mb = target_path.stat().st_size / (1024 * 1024)
                logger.info(f"  -> [hf_hub] 完成: {target_path.name} ({size_mb:.1f} MB)")
                return True
            else:
                logger.error(f"  -> [ERROR] 下载完成但文件不存在: {target_path}")
                return False
        finally:
            # 清理临时目录（含嵌套子路径和 .cache 元数据，一次全删干净）
            if staging_dir and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
                logger.debug(f"  -> [hf_hub] 已清理临时目录: {staging_dir}")

    # ── 缓存管理 ─────────────────────────────────────────────

    def cache_info(self) -> List[CacheEntry]:
        """返回 HF Hub 缓存、Xet 缓存和下载临时目录的条目信息"""
        entries = [
            (self._HF_HUB_CACHE, "HuggingFace Hub 缓存"),
            (self._HF_DL_CACHE,  "HuggingFace 下载临时"),
            (self._HF_XET_CACHE, "HuggingFace Xet 缓存"),
        ]
        return [
            CacheEntry(
                name=name,
                path=path,
                size_bytes=_calc_dir_size(path),
                exists=path.exists(),
            )
            for path, name in entries
        ]

    def purge_cache(self, pattern: Optional[str] = None) -> List[PurgeResult]:
        """清理 HF Hub 缓存
        
        Args:
            pattern: 若指定，只删除 hub 目录下匹配 models--*{pattern}* 的子目录；
                     否则删除整个 hub 缓存目录。
        """
        results: List[PurgeResult] = []

        # ── Hub 缓存 ──────────────────────────────────────
        if self._HF_HUB_CACHE.exists():
            if pattern:
                for model_dir in self._HF_HUB_CACHE.glob(f"models--*{pattern}*"):
                    size = _calc_dir_size(model_dir)
                    try:
                        shutil.rmtree(model_dir)
                        results.append(PurgeResult(str(model_dir), size, True))
                    except OSError as e:
                        results.append(PurgeResult(str(model_dir), 0, False, str(e)))
            else:
                size = _calc_dir_size(self._HF_HUB_CACHE)
                try:
                    shutil.rmtree(self._HF_HUB_CACHE)
                    results.append(PurgeResult(str(self._HF_HUB_CACHE), size, True))
                except OSError as e:
                    results.append(PurgeResult(str(self._HF_HUB_CACHE), 0, False, str(e)))

        # ── 下载临时目录（无论 pattern 均清理）────────────
        if self._HF_DL_CACHE.exists():
            size = _calc_dir_size(self._HF_DL_CACHE)
            try:
                shutil.rmtree(self._HF_DL_CACHE)
                results.append(PurgeResult(str(self._HF_DL_CACHE), size, True))
            except OSError as e:
                results.append(PurgeResult(str(self._HF_DL_CACHE), 0, False, str(e)))

        # ── Xet 缓存目录（无论 pattern 均清理）────────────
        if self._HF_XET_CACHE.exists():
            size = _calc_dir_size(self._HF_XET_CACHE)
            try:
                shutil.rmtree(self._HF_XET_CACHE)
                results.append(PurgeResult(str(self._HF_XET_CACHE), size, True))
            except OSError as e:
                results.append(PurgeResult(str(self._HF_XET_CACHE), 0, False, str(e)))

        return results

    def purge_model_cache(self, repo_id: str) -> Optional[PurgeResult]:
        """精准清理指定模型的 Hub 缓存
        
        Args:
            repo_id: 如 "black-forest-labs/FLUX.2-klein-9B"
            
        Returns:
            PurgeResult 或 None（缓存不存在时）
        """
        cache_name = f"models--{repo_id.replace('/', '--')}"
        cache_dir  = self._HF_HUB_CACHE / cache_name

        if not cache_dir.exists():
            return None

        size = _calc_dir_size(cache_dir)
        try:
            shutil.rmtree(cache_dir)
            logger.info(f"  -> [hf_hub] 已清理: {cache_name} ({size / 1024 / 1024:.1f} MB)")
            return PurgeResult(str(cache_dir), size, True)
        except OSError as e:
            logger.error(f"  -> [ERROR] 清理失败: {e}")
            return PurgeResult(str(cache_dir), 0, False, str(e))

    # ── 内部工具 ─────────────────────────────────────────────

    def _clear_hf_locks(self, target_dir: Path) -> None:
        """清理全局与局部 HF 锁文件，防止死锁"""
        # 1. 全局 HF_HOME 锁目录
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            global_lock_dir = Path(hf_home) / "hub" / ".locks"
            if global_lock_dir.exists():
                try:
                    shutil.rmtree(global_lock_dir)
                    logger.debug("  -> [hf_hub] 已清理全局 HF 锁目录")
                except OSError as e:
                    logger.debug(f"  -> [hf_hub] 清理全局锁失败: {e}")

        # 2. local_dir 下的局部锁文件
        local_cache = target_dir / ".cache" / "huggingface"
        if local_cache.exists():
            for lock_file in local_cache.rglob("*.lock"):
                try:
                    lock_file.unlink()
                    logger.debug(f"  -> [hf_hub] 解除局部锁: {lock_file.name}")
                except OSError as e:
                    logger.debug(f"  -> [hf_hub] 解除局部锁失败 {lock_file.name}: {e}")

    def _cleanup_nested_dirs(self, target_dir: Path, filename: str) -> None:
        """清理 filename 含子路径时产生的嵌套空目录"""
        if not filename or "/" not in filename:
            return
        first_sub = filename.split("/")[0]
        nested = target_dir / first_sub
        if nested.exists() and nested.is_dir():
            self._remove_empty_dirs(nested)

    def _remove_empty_dirs(self, path: Path) -> None:
        """递归删除空目录"""
        if not path.is_dir():
            return
        for child in list(path.iterdir()):
            if child.is_dir():
                self._remove_empty_dirs(child)
        if not any(path.iterdir()):
            try:
                path.rmdir()
                logger.debug(f"  -> [hf_hub] 已清理空目录: {path.name}")
            except OSError:
                pass
