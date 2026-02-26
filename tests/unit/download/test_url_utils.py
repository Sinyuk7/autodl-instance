"""
URL 解析工具测试

覆盖核心场景：HF URL 解析、URL 类型检测
"""
import pytest

from src.lib.download.url_utils import (
    parse_hf_url,
    detect_url_type,
)


class TestParseHfUrl:
    """HuggingFace URL 解析测试"""
    
    def test_standard_model_url(self):
        """标准模型 URL 解析"""
        url = "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
        result = parse_hf_url(url)
        
        assert result is not None
        repo_id, filename, revision, repo_type = result
        assert repo_id == "black-forest-labs/FLUX.1-dev"
        assert filename == "flux1-dev.safetensors"
        assert revision == "main"
        assert repo_type is None
    
    def test_dataset_url(self):
        """Dataset URL 解析 - repo_type 为 dataset"""
        url = "https://huggingface.co/datasets/my-org/my-dataset/resolve/main/data.parquet"
        result = parse_hf_url(url)
        
        assert result is not None
        repo_id, _, _, repo_type = result
        assert repo_id == "my-org/my-dataset"
        assert repo_type == "dataset"
    
    def test_nested_filename(self):
        """嵌套路径文件名解析"""
        url = "https://huggingface.co/org/repo/resolve/main/models/unet/model.safetensors"
        result = parse_hf_url(url)
        
        assert result is not None
        _, filename, _, _ = result
        assert filename == "models/unet/model.safetensors"
    
    def test_invalid_url_returns_none(self):
        """无效 URL 返回 None"""
        assert parse_hf_url("https://example.com/file.bin") is None
        assert parse_hf_url("https://huggingface.co/org/repo") is None


class TestDetectUrlType:
    """URL 类型检测测试"""
    
    def test_url_type_detection(self):
        """各类型 URL 正确检测"""
        assert detect_url_type("https://huggingface.co/org/repo/resolve/main/file.bin") == "huggingface"
        assert detect_url_type("https://civitai.com/api/download/models/12345") == "civitai"
        assert detect_url_type("https://example.com/file.bin") == "direct"