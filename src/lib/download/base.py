"""
下载策略抽象基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ============================================================
# 缓存相关数据类
# ============================================================

@dataclass
class CacheEntry:
    """单个缓存条目信息"""
    name: str           # 展示名，如 "HuggingFace Hub"
    path: Path          # 缓存根路径
    size_bytes: int     # 已计算好的大小（由策略自行计算）
    exists: bool        # 路径是否存在


@dataclass
class PurgeResult:
    """单次缓存清理结果"""
    path: str               # 被清理的路径（字符串，便于展示）
    freed_bytes: int        # 实际释放的字节数
    success: bool           # 是否成功
    error: Optional[str] = field(default=None)  # 失败时的错误信息


# ============================================================
# 下载策略抽象基类
# ============================================================

class DownloadStrategy(ABC):
    """下载策略抽象基类
    
    每个具体策略负责:
      1. 自身可用性检测与依赖安装
      2. 文件下载（含 dry_run 预估模式）
      3. 下载前准备与异常清理
      4. 自身缓存的查询与清理（cache_info / purge_cache）
      5. 自身配置的加载（各策略在 __init__ 中自行读取）
    """

    # ── 元信息 ──────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """策略唯一名称，如 'hf_hub'、'aria2'、'wget'"""
        ...

    # ── 可用性 ──────────────────────────────────────────────

    @abstractmethod
    def is_available(self) -> bool:
        """检查策略当前是否可用（依赖已安装）"""
        ...

    def ensure_available(self) -> bool:
        """确保策略可用，必要时自动安装依赖
        
        Returns:
            True 可用，False 无法安装
        """
        return self.is_available()

    # ── 下载（核心）─────────────────────────────────────────

    @abstractmethod
    def download(self, url: str, target_path: Path, dry_run: bool = False) -> bool:
        """执行下载
        
        Args:
            url:         下载链接
            target_path: 目标文件完整路径
            dry_run:     若为 True，仅预估不实际下载（各策略尽力支持）
            
        Returns:
            True 成功（dry_run 时表示"执行将会成功"），False 失败
        """
        ...

    def pre_download(self, target_path: Path) -> None:
        """下载前的准备工作（由 Manager 调用）
        
        子类可覆盖此方法执行清理锁文件、创建目录、注入环境变量等操作。
        注意：此方法由 DownloadManager 在调用 download() 前统一调用。
        """
        pass

    def post_download(self, target_path: Path) -> None:
        """下载成功后的收尾工作（由 Manager 调用）
        
        子类可覆盖此方法处理文件重命名、清理元数据目录、
        校验完整性等操作。
        注意：此方法由 DownloadManager 在 download() 成功后统一调用。
        """
        pass

    def on_interrupt(self, target_path: Path) -> None:
        """用户中断（Ctrl+C）时的清理逻辑（由 Manager 调用）
        
        子类可覆盖此方法清理锁文件、临时目录等。
        注意：
          - 仅在 KeyboardInterrupt 时调用，普通异常不调用
          - 不应删除下载缓存，以支持断点续传
          - 此方法由 DownloadManager 统一调用
        """
        pass

    # ── 缓存管理（各策略自治）───────────────────────────────

    def cache_info(self) -> List[CacheEntry]:
        """返回本策略管理的所有缓存条目（含大小）
        
        默认返回空列表，无缓存的策略（如 wget）无需覆盖。
        """
        return []

    def purge_cache(self, pattern: Optional[str] = None) -> List[PurgeResult]:
        """清理本策略管理的缓存
        
        Args:
            pattern: 匹配模式（如 "FLUX" 只清理包含 FLUX 的条目），
                     None 表示清理全部
                     
        Returns:
            每次删除操作的结果列表
        """
        return []