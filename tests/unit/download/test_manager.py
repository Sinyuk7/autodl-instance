"""
DownloadManager 测试

覆盖核心场景：策略选择逻辑、生命周期编排
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from src.lib.download.manager import DownloadManager
from src.lib.download.base import DownloadStrategy


class TestStrategySelection:
    """策略选择逻辑测试 - 所有 URL 统一使用 aria2"""
    
    def test_all_urls_select_aria2(self):
        """所有 URL 类型统一使用 aria2 策略"""
        manager = DownloadManager()
        
        # 测试各种 URL 类型都返回 aria2 策略
        urls = [
            "https://huggingface.co/org/repo/resolve/main/model.safetensors",
            "https://example.com/model.bin",
            "https://civitai.com/api/download/models/12345",
        ]
        
        for url in urls:
            strategy = manager.get_strategy(url)
            assert strategy.name == "aria2", f"URL {url} should use aria2 strategy"
    
    def test_direct_url_selects_aria2(self):
        """直链 URL → 选择 aria2"""
        manager = DownloadManager()
        
        with patch.object(manager._strategies["aria2"], 'is_available', return_value=True):
            strategy = manager.get_strategy("https://example.com/model.bin")
        
        assert strategy.name == "aria2"
    
    def test_civitai_url_selects_aria2(self):
        """CivitAI URL → 选择 aria2"""
        manager = DownloadManager()
        
        with patch.object(manager._strategies["aria2"], 'is_available', return_value=True):
            strategy = manager.get_strategy(
                "https://civitai.com/api/download/models/12345"
            )
        
        assert strategy.name == "aria2"


class TestDownloadLifecycle:
    """下载生命周期编排测试"""
    
    def test_successful_download_lifecycle(self, tmp_path: Path):
        """成功下载：pre_download → download → post_download"""
        manager = DownloadManager()
        target = tmp_path / "model.safetensors"
        url = "https://example.com/model.safetensors"
        
        # 创建 mock 策略
        mock_strategy = MagicMock(spec=DownloadStrategy)
        mock_strategy.name = "mock"
        mock_strategy.download.return_value = True
        
        with patch.object(manager, 'get_strategy', return_value=mock_strategy), \
             patch.object(manager, '_ensure_tools'):
            result = manager.download(url, target, dry_run=False)
        
        assert result is True
        # 验证调用顺序
        mock_strategy.pre_download.assert_called_once_with(target)
        mock_strategy.download.assert_called_once_with(url, target, dry_run=False)
        mock_strategy.post_download.assert_called_once_with(target)
    
    def test_failed_download_no_post_download(self, tmp_path: Path):
        """下载失败时不调用 post_download"""
        manager = DownloadManager()
        target = tmp_path / "model.safetensors"
        
        mock_strategy = MagicMock(spec=DownloadStrategy)
        mock_strategy.name = "mock"
        mock_strategy.download.return_value = False
        
        with patch.object(manager, 'get_strategy', return_value=mock_strategy), \
             patch.object(manager, '_ensure_tools'):
            result = manager.download("https://example.com/model.bin", target)
        
        assert result is False
        mock_strategy.post_download.assert_not_called()
    
    def test_dry_run_skips_lifecycle(self, tmp_path: Path):
        """dry_run 模式跳过生命周期管理"""
        manager = DownloadManager()
        target = tmp_path / "model.safetensors"
        
        mock_strategy = MagicMock(spec=DownloadStrategy)
        mock_strategy.name = "mock"
        mock_strategy.download.return_value = True
        
        with patch.object(manager, 'get_strategy', return_value=mock_strategy), \
             patch.object(manager, '_ensure_tools'):
            manager.download("https://example.com/model.bin", target, dry_run=True)
        
        mock_strategy.pre_download.assert_not_called()
        mock_strategy.post_download.assert_not_called()


class TestCacheAggregation:
    """缓存聚合测试"""
    
    def test_cache_info_returns_aria2_entries(self):
        """cache_info 返回 Aria2 缓存条目"""
        manager = DownloadManager()
        
        # 调用实际的 cache_info
        entries = manager.cache_info()
        
        # 应该包含 Aria2 的缓存条目
        names = [e.name for e in entries]
        assert any("Aria2" in name for name in names)