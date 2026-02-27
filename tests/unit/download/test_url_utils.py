"""
URL 解析工具测试

覆盖核心场景：URL 类型检测、文件名提取
"""
import pytest

from src.lib.download.url_utils import (
    detect_url_type,
    extract_filename_from_url,
)


class TestDetectUrlType:
    """URL 类型检测测试"""
    
    def test_url_type_detection(self):
        """各类型 URL 正确检测"""
        assert detect_url_type("https://huggingface.co/org/repo/resolve/main/file.bin") == "huggingface"
        assert detect_url_type("https://civitai.com/api/download/models/12345") == "civitai"
        assert detect_url_type("https://example.com/file.bin") == "direct"


class TestExtractFilenameFromUrl:
    """URL 文件名提取测试"""
    
    def test_huggingface_url(self):
        """从 HuggingFace URL 提取文件名"""
        url = "https://huggingface.co/org/repo/resolve/main/model.safetensors"
        assert extract_filename_from_url(url) == "model.safetensors"
    
    def test_direct_url(self):
        """从直链 URL 提取文件名"""
        url = "https://example.com/path/to/model.ckpt"
        assert extract_filename_from_url(url) == "model.ckpt"
    
    def test_civitai_url_returns_empty(self):
        """CivitAI 下载 URL 返回空（无文件名）"""
        url = "https://civitai.com/api/download/models/12345"
        assert extract_filename_from_url(url) == ""
    
    def test_url_without_extension_returns_empty(self):
        """无扩展名的路径返回空"""
        url = "https://example.com/path/to/file"
        assert extract_filename_from_url(url) == ""