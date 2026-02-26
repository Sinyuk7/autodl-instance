"""
下载管理器 - 根据 URL 自动选择最佳策略

特性:
  - 自动检测 URL 类型选择最佳策略
  - 懒加载安装（首次使用时检查并安装依赖）
  - 支持 HuggingFace, CivitAI, 直链
  - 缓存管理聚合（遍历各策略，无硬编码路径）
"""
import logging
from pathlib import Path
from typing import List, Optional

from src.lib.download.base import CacheEntry, DownloadStrategy, PurgeResult
from src.lib.download.hf_hub import HuggingFaceHubStrategy
from src.lib.download.aria2 import Aria2Strategy
from src.lib.download.url_utils import detect_url_type

logger = logging.getLogger("autodl_setup")


class DownloadManager:
    """下载管理器 - 根据 URL 自动选择最佳策略

    策略优先级:
      1. HuggingFace URL → HuggingFaceHubStrategy（hf_xet 自动加速）
      2. 所有 URL       → Aria2Strategy（多线程）
    """

    def __init__(self) -> None:
        # 各策略自行加载配置，manager 只负责组装
        self._hf_strategy    = HuggingFaceHubStrategy()
        self._aria2_strategy = Aria2Strategy()

        # 所有策略列表，供缓存聚合使用
        self._all_strategies: List[DownloadStrategy] = [
            self._hf_strategy,
            self._aria2_strategy,
        ]

        self._initialized = False

    # ── 懒加载 ──────────────────────────────────────────────

    def _ensure_tools(self) -> None:
        """首次下载时懒加载安装依赖工具"""
        if self._initialized:
            return
        self._initialized = True

        if not self._aria2_strategy.is_available():
            self._aria2_strategy.ensure_available()

        if self._hf_strategy.is_available():
            self._hf_strategy.ensure_available()

    # ── 策略选择 ─────────────────────────────────────────────

    def get_strategy(self, url: str) -> DownloadStrategy:
        """根据 URL 选择最佳下载策略"""
        url_type = detect_url_type(url)

        if url_type == "huggingface" and self._hf_strategy.is_available():
            return self._hf_strategy

        if self._aria2_strategy.is_available():
            return self._aria2_strategy

        # aria2 不可用时回退到 hf_strategy（仅支持 HF URL），下载时会有明确报错
        return self._hf_strategy

    # ── 下载 ─────────────────────────────────────────────────

    def download(self, url: str, target_path: Path, dry_run: bool = False) -> bool:
        """下载文件

        Args:
            url:         下载链接
            target_path: 目标文件完整路径
            dry_run:     仅预估，不实际下载

        Returns:
            True 成功，False 失败
        """
        self._ensure_tools()
        strategy = self.get_strategy(url)
        logger.info(f"  -> 使用策略: {strategy.name}")

        # dry_run 模式不需要生命周期管理
        if dry_run:
            return strategy.download(url, target_path, dry_run=True)

        # 统一编排生命周期
        strategy.pre_download(target_path)

        try:
            success = strategy.download(url, target_path, dry_run=False)
            if success:
                strategy.post_download(target_path)
            return success

        except KeyboardInterrupt:
            # 用户中断，清理锁文件等（保留缓存以支持断点续传）
            logger.info("\n  -> 下载被用户中断，正在清理...")
            strategy.on_interrupt(target_path)
            logger.info("  -> 清理完成，可重新运行以继续下载。")
            return False

    # ── 缓存管理（聚合所有策略）─────────────────────────────

    def cache_info(self) -> List[CacheEntry]:
        """聚合所有策略的缓存条目信息"""
        entries: List[CacheEntry] = []
        for strategy in self._all_strategies:
            entries.extend(strategy.cache_info())
        return entries

    def purge_cache(
        self,
        cache_type: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> List[PurgeResult]:
        """聚合清理所有（或指定类型）策略的缓存

        Args:
            cache_type: 策略名称过滤（如 "hf_hub"、"aria2"），None 表示全部
            pattern:    传递给各策略的匹配模式

        Returns:
            所有策略的清理结果合并列表
        """
        results: List[PurgeResult] = []
        for strategy in self._all_strategies:
            if cache_type and strategy.name != cache_type:
                continue
            results.extend(strategy.purge_cache(pattern=pattern))
        return results

    def purge_model_cache(self, repo_id: str) -> Optional[PurgeResult]:
        """精准清理指定 HuggingFace 模型的缓存

        Args:
            repo_id: 如 "black-forest-labs/FLUX.2-klein-9B"
        """
        return self._hf_strategy.purge_model_cache(repo_id)


# ============================================================
# 全局便捷函数
# ============================================================

_download_manager: Optional[DownloadManager] = None


def _get_manager() -> DownloadManager:
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager()
    return _download_manager


def download_model(url: str, target_path: Path, dry_run: bool = False) -> bool:
    """下载模型文件（全局入口）"""
    return _get_manager().download(url, target_path, dry_run=dry_run)


def cache_info() -> List[CacheEntry]:
    """获取所有下载缓存信息"""
    return _get_manager().cache_info()


def purge_cache(
    cache_type: Optional[str] = None,
    pattern: Optional[str] = None,
) -> List[PurgeResult]:
    """清理下载缓存"""
    return _get_manager().purge_cache(cache_type=cache_type, pattern=pattern)


def purge_model_cache(repo_id: str) -> Optional[PurgeResult]:
    """清理指定 HuggingFace 模型缓存"""
    return _get_manager().purge_model_cache(repo_id)