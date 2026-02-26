"""
高速下载模块

支持的下载策略:
  - HuggingFace URL: huggingface_hub + hf_xet（chunk-based 加速）
  - CivitAI / 直链:  aria2c 多线程下载
  - Fallback:        wget 单线程

缓存管理:
  - cache_info():         获取所有策略的缓存信息
  - purge_cache():        清理下载缓存（支持按策略类型和 pattern 过滤）
  - purge_model_cache():  精准清理指定 HF 模型缓存
"""
from src.lib.download.manager import (
    DownloadManager,
    download_model,
    cache_info,
    purge_cache,
    purge_model_cache,
)
from src.lib.download.url_utils import (
    detect_url_type,
    parse_hf_url,
    extract_filename_from_url,
)
from src.lib.download.base import CacheEntry, PurgeResult

__all__ = [
    # 下载
    "DownloadManager",
    "download_model",
    # URL 工具
    "detect_url_type",
    "parse_hf_url",
    "extract_filename_from_url",
    # 缓存管理
    "cache_info",
    "purge_cache",
    "purge_model_cache",
    # 数据类
    "CacheEntry",
    "PurgeResult",
]