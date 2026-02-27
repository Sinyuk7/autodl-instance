"""
URL 解析和检测工具
"""
from urllib.parse import unquote, urlparse


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
