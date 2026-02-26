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
    """策略选择逻辑测试"""
    
    def test_hf_url_selects_hf_strategy_when_available(self):
        """HF URL + HF 策略可用 → 选择 hf_hub"""
        manager = DownloadManager()
        manager._hf_strategy._enabled = True
        
        with patch.object(manager._hf_strategy, 'is_available', return_value=True):
            strategy = manager.get_strategy(
                "https://huggingface.co/org/repo/resolve/main/model.safetensors"
            )
        
        assert strategy.name == "hf_hub"
    
    def test_hf_url_fallback_to_aria2_when_hf_unavailable(self):
        """HF URL + HF 不可用 → 回退 aria2"""
        manager = DownloadManager()
        
        with patch.object(manager._hf_strategy, 'is_available', return_value=False), \
             patch.object(manager._aria2_strategy, 'is_available', return_value=True):
            strategy = manager.get_strategy(
                "https://huggingface.co/org/repo/resolve/main/model.safetensors"
            )
        
        assert strategy.name == "aria2"
    
    def test_direct_url_selects_aria2(self):
        """直链 URL → 选择 aria2"""
        manager = DownloadManager()
        
        with patch.object(manager._aria2_strategy, 'is_available', return_value=True):
            strategy = manager.get_strategy("https://example.com/model.bin")
        
        assert strategy.name == "aria2"
    
    def test_civitai_url_selects_aria2(self):
        """CivitAI URL → 选择 aria2"""
        manager = DownloadManager()
        
        with patch.object(manager._aria2_strategy, 'is_available', return_value=True):
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
    
    def test_cache_info_aggregates_all_strategies(self):
        """cache_info 聚合所有策略的缓存条目"""
        manager = DownloadManager()
        
        # 调用实际的 cache_info
        entries = manager.cache_info()
        
        # 应该包含 HF 和 Aria2 的缓存条目
        names = [e.name for e in entries]
        assert any("HuggingFace" in name for name in names)
        assert any("Aria2" in name for name in names)
