"""
下载策略测试

覆盖核心场景：Aria2 策略的可用性检测、缓存管理
"""
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.lib.download.aria2 import Aria2Strategy
from src.lib.download.base import CacheEntry


class TestAria2Strategy:
    """Aria2 策略测试"""
    
    def test_name_property(self):
        """策略名称正确"""
        strategy = Aria2Strategy()
        assert strategy.name == "aria2"
    
    def test_is_available_when_aria2c_exists(self):
        """aria2c 可执行时可用"""
        strategy = Aria2Strategy()
        
        with patch.object(shutil, 'which', return_value='/usr/bin/aria2c'):
            assert strategy.is_available() is True
    
    def test_is_available_when_aria2c_missing(self):
        """aria2c 不存在时不可用"""
        strategy = Aria2Strategy()
        
        with patch.object(shutil, 'which', return_value=None):
            assert strategy.is_available() is False
    
    def test_cache_info_returns_correct_structure(self):
        """cache_info 返回正确结构
        
        aria2 不产生持久化缓存目录，cache_info 返回空列表
        """
        strategy = Aria2Strategy()
        entries = strategy.cache_info()
        
        assert isinstance(entries, list)
        assert len(entries) == 0  # aria2 无持久化缓存
    
    def test_pre_download_creates_parent_dir(self, tmp_path: Path):
        """pre_download 创建父目录"""
        strategy = Aria2Strategy()
        target = tmp_path / "subdir" / "model.bin"
        
        assert not target.parent.exists()
        strategy.pre_download(target)
        assert target.parent.exists()
    
    def test_post_download_cleans_aria2_control_file(self, tmp_path: Path):
        """post_download 清理 .aria2 控制文件"""
        strategy = Aria2Strategy()
        target = tmp_path / "model.bin"
        control_file = tmp_path / "model.bin.aria2"
        
        # 创建模拟的控制文件
        target.touch()
        control_file.touch()
        
        strategy.post_download(target)
        
        assert not control_file.exists()
