"""
下载管理器 - 根据 URL 自动选择最佳策略

特性:
  - 策略模式设计，易于扩展新的下载方式
  - 自动检测 URL 类型选择最佳策略
  - 懒加载安装（首次使用时检查并安装依赖）
  - 缓存管理聚合（遍历各策略，无硬编码路径）

扩展新策略:
  1. 创建新策略类，继承 DownloadStrategy
  2. 在 _register_strategies() 中注册
  3. 在 get_strategy() 中添加选择逻辑
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.lib.download.base import CacheEntry, DownloadStrategy, PurgeResult
from src.lib.download.aria2 import Aria2Strategy
from src.lib.download.url_utils import detect_url_type

logger = logging.getLogger("autodl_setup")


class DownloadManager:
    """下载管理器 - 根据 URL 自动选择最佳策略
    
    设计原则:
      - 策略模式: 每种下载方式实现 DownloadStrategy 接口
      - 开闭原则: 新增策略只需注册，无需修改核心下载逻辑
      - 懒加载: 首次下载时才安装依赖工具
    
    当前支持的策略:
      - aria2: 多线程 HTTP/HTTPS 下载（默认）
    
    扩展示例（添加 wget 策略）:
      1. 创建 src/lib/download/wget.py，实现 WgetStrategy(DownloadStrategy)
      2. 在 _register_strategies() 中添加: self._strategies["wget"] = WgetStrategy()
      3. 在 get_strategy() 中添加选择逻辑
    """

    def __init__(self) -> None:
        # 策略注册表: name -> strategy instance
        self._strategies: Dict[str, DownloadStrategy] = {}
        self._register_strategies()
        
        # 默认策略（当其他策略都不可用时的回退）
        self._default_strategy_name = "aria2"
        
        self._initialized = False

    def _register_strategies(self) -> None:
        """注册所有可用的下载策略
        
        扩展点: 新增策略时在此注册
        """
        self._strategies["aria2"] = Aria2Strategy()
        
        # 示例: 未来可以添加更多策略
        # self._strategies["wget"] = WgetStrategy()
        # self._strategies["curl"] = CurlStrategy()

    @property
    def _all_strategies(self) -> List[DownloadStrategy]:
        """所有已注册策略的列表"""
        return list(self._strategies.values())

    # ── 懒加载 ──────────────────────────────────────────────

    def _ensure_tools(self) -> None:
        """首次下载时懒加载安装依赖工具"""
        if self._initialized:
            return
        self._initialized = True

        # 确保默认策略可用
        default_strategy = self._strategies.get(self._default_strategy_name)
        if default_strategy and not default_strategy.is_available():
            default_strategy.ensure_available()

    # ── 策略选择 ─────────────────────────────────────────────

    def get_strategy(self, url: str) -> DownloadStrategy:
        """根据 URL 选择最佳下载策略
        
        选择逻辑（按优先级）:
          1. 根据 URL 类型匹配特定策略（如有）
          2. 回退到默认策略
        
        扩展点: 添加新策略的选择逻辑
        
        Args:
            url: 下载链接
            
        Returns:
            最适合的下载策略实例
        """
        _url_type = detect_url_type(url)
        
        # ── 策略选择逻辑 ──
        # 扩展示例: 
        # if _url_type == "magnet" and "torrent" in self._strategies:
        #     strategy = self._strategies["torrent"]
        #     if strategy.is_available():
        #         return strategy
        
        # 默认: 所有 URL 类型使用 aria2 多线程下载
        return self._strategies[self._default_strategy_name]

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

    def purge_cache(self) -> List[PurgeResult]:
        """聚合清理所有策略的缓存

        Returns:
            所有策略的清理结果合并列表
        """
        results: List[PurgeResult] = []
        for strategy in self._all_strategies:
            results.extend(strategy.purge_cache())
        return results


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


def purge_cache() -> List[PurgeResult]:
    """清理下载缓存"""
    return _get_manager().purge_cache()
