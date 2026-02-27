"""
高速下载模块

支持的下载策略:
  - 所有 URL:  aria2c 多线程下载

缓存管理:
  - cache_info():  获取所有策略的缓存信息
  - purge_cache(): 清理下载缓存（支持按策略类型和 pattern 过滤）
"""
from src.lib.download.manager import (
    DownloadManager,
    download_model,
    cache_info,
    purge_cache,
)
from src.lib.download.url_utils import (
    detect_url_type,
    extract_filename_from_url,
)
from src.lib.download.base import CacheEntry, PurgeResult

__all__ = [
    # 下载
    "DownloadManager",
    "download_model",
    # URL 工具
    "detect_url_type",
    "extract_filename_from_url",
    # 缓存管理
    "cache_info",
    "purge_cache",
    # 数据类
    "CacheEntry",
    "PurgeResult",
]