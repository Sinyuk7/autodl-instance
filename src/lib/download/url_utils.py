"""
URL 解析和检测工具
"""
import re
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse


def parse_hf_url(url: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """解析 HuggingFace URL
    
    支持格式:
      https://huggingface.co/{org}/{repo}/resolve/{revision}/{filename}
      https://huggingface.co/{org}/{repo}/blob/{revision}/{filename}
      https://huggingface.co/datasets/{org}/{repo}/resolve/{revision}/{filename}
      https://huggingface.co/spaces/{org}/{repo}/resolve/{revision}/{filename}
    
    Returns:
        (repo_id, filename, revision, repo_type) 或 None
    """
    pattern = r"https?://huggingface\.co/(?:(datasets|spaces)/)?([^/]+/[^/]+)/(?:resolve|blob)/([^/]+)/(.+)"
    match = re.match(pattern, url)
    if not match:
        return None
    
    repo_type_raw = match.group(1) # "datasets" or "spaces" or None
    repo_type = repo_type_raw[:-1] if repo_type_raw else None # "dataset" or "space" or None
    repo_id = match.group(2)      # e.g., "black-forest-labs/FLUX.2-klein-9B"
    revision = match.group(3)      # e.g., "main"
    filename = unquote(match.group(4))  # e.g., "flux-2-klein-9b.safetensors"
    
    return (repo_id, filename, revision, repo_type)


def extract_filename_from_url(url: str) -> str:
    """从 URL 提取文件名
    
    支持:
    - HuggingFace: https://huggingface.co/.../resolve/main/model.safetensors
    - CivitAI: https://civitai.com/api/download/models/12345 (返回空)
    - 直链: https://example.com/path/to/model.ckpt
    
    Returns:
        文件名，或空字符串
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if "/" in path:
        filename = path.rsplit("/", 1)[-1]
        # 检查是否有效
        if filename and "." in filename:
            return filename
    return ""


def detect_url_type(url: str) -> str:
    """检测 URL 类型
    
    Returns:
        "huggingface", "civitai", 或 "direct"
    """
    if "huggingface.co" in url:
        return "huggingface"
    elif "civitai.com" in url:
        return "civitai"
    else:
        return "direct"
