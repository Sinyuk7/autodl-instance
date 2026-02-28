"""
CivitAI API 工具

参考 comfy-cli 实现，增强错误处理和类型推断
"""
import logging
import os
from typing import Any, Dict, Optional, Tuple, TypedDict
from urllib.parse import parse_qs, urlparse

import requests

from src.core.schema import EnvKey

ENV_CIVITAI_TOKEN = EnvKey.CIVITAI_API_TOKEN
from src.lib.ui import print_warning

logger = logging.getLogger("autodl_setup")


# CivitAI 模型类型 -> ComfyUI 目录映射
CIVITAI_TYPE_MAP = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "locon": "loras",  # LyCORIS 也放 loras
    "hypernetwork": "hypernetworks",
    "textualinversion": "embeddings",
    "embedding": "embeddings",
    "controlnet": "controlnet",
    "vae": "vae",
    "upscaler": "upscale_models",
    "poses": "poses",
    "wildcards": "wildcards",
    "workflows": "workflows",
    "other": "other",
}


def get_api_token() -> Optional[str]:
    """获取 CivitAI API Token"""
    return os.environ.get(ENV_CIVITAI_TOKEN)


def _log_request_context() -> None:
    """记录 API 请求上下文（代理状态等）"""
    proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    if proxy:
        logger.debug(f"  -> [CivitAI API] 使用代理: {proxy}")
    else:
        logger.debug("  -> [CivitAI API] 未配置代理")


class CivitaiUrlInfo(TypedDict):
    """CivitAI URL 解析结果类型"""

    is_civitai: bool
    is_model_page: bool
    is_api_url: bool
    model_id: Optional[int]
    version_id: Optional[int]


def parse_civitai_url(url: str) -> CivitaiUrlInfo:
    """解析 CivitAI URL
    
    支持格式:
      - https://civitai.com/models/12345
      - https://civitai.com/models/12345/model-name
      - https://civitai.com/models/12345?modelVersionId=67890
      - https://civitai.com/api/download/models/67890
      - https://civitai.com/api/v1/model-versions/67890
      
    Returns:
        CivitaiUrlInfo 类型字典
    """
    result: CivitaiUrlInfo = {
        "is_civitai": False,
        "is_model_page": False,
        "is_api_url": False,
        "model_id": None,
        "version_id": None,
    }
    
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        
        if host != "civitai.com" and not host.endswith(".civitai.com"):
            return result
        
        result["is_civitai"] = True
        path_parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        
        # Case 1: /api/download/models/<version_id>
        if len(path_parts) >= 4 and path_parts[0] == "api":
            if path_parts[1] == "download" and path_parts[2] == "models":
                result["is_api_url"] = True
                try:
                    result["version_id"] = int(path_parts[3])
                except ValueError:
                    pass
                return result
            
            # Case 2: /api/v1/model-versions/<version_id>
            if path_parts[1] == "v1" and path_parts[2] in ("model-versions", "modelVersions"):
                result["is_api_url"] = True
                try:
                    result["version_id"] = int(path_parts[3])
                except ValueError:
                    pass
                return result
        
        # Case 3: /models/<model_id>
        if len(path_parts) >= 2 and path_parts[0] == "models":
            result["is_model_page"] = True
            try:
                result["model_id"] = int(path_parts[1])
            except ValueError:
                return result
            
            # 检查 query 参数中的 version_id
            for key in ("modelVersionId", "version"):
                if key in query and query[key]:
                    try:
                        result["version_id"] = int(query[key][0])
                        break
                    except ValueError:
                        pass
        
        return result
        
    except Exception:
        return result


def fetch_model_info_by_version(version_id: int) -> Optional[Dict[str, Any]]:
    """通过 version_id 获取模型信息
    
    Returns:
        {
            "filename": str,
            "download_url": str,
            "model_type": str,      # 原始类型 (如 "LORA")
            "comfy_type": str,      # ComfyUI 目录 (如 "loras")
            "base_model": str,      # 如 "SD1.5", "SDXL", "Pony"
            "size_kb": int,
            # 新增的元数据字段
            "model_id": int,        # CivitAI 模型 ID
            "version_id": int,      # CivitAI 版本 ID
            "model_name": str,      # 模型名称
            "version_name": str,    # 版本名称
            "trigger_words": list,  # 触发词列表
            "sha256": str,          # 文件 SHA256 哈希
        }
    """
    # 记录请求上下文
    _log_request_context()
    
    headers = {"Content-Type": "application/json"}
    token = get_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        response = requests.get(
            f"https://civitai.com/api/v1/model-versions/{version_id}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        
        # 查找主文件
        primary_file = None
        for f in data.get("files", []):
            if f.get("primary", False):
                primary_file = f
                break
        
        if not primary_file and data.get("files"):
            primary_file = data["files"][0]
        
        if not primary_file:
            return None
        
        model_info = data.get("model", {})
        model_type_raw = model_info.get("type", "other").lower()
        base_model = data.get("baseModel", "unknown").replace(" ", "")
        
        # 提取文件哈希 (优先 SHA256)
        hashes = primary_file.get("hashes", {})
        sha256 = hashes.get("SHA256", "")
        
        # 提取触发词
        trigger_words = data.get("trainedWords", [])
        
        return {
            "filename": primary_file.get("name", ""),
            "download_url": primary_file.get("downloadUrl", ""),
            "model_type": model_type_raw,
            "comfy_type": CIVITAI_TYPE_MAP.get(model_type_raw, "other"),
            "base_model": base_model,
            "size_kb": primary_file.get("sizeKB", 0),
            # 新增的元数据字段
            "model_id": model_info.get("id"),
            "version_id": data.get("id"),
            "model_name": model_info.get("name", ""),
            "version_name": data.get("name", ""),
            "trigger_words": trigger_words if trigger_words else [],
            "sha256": sha256,
        }
        
    except requests.RequestException as e:
        print_warning(f"CivitAI API 请求失败: {e}")
        return None


def fetch_model_info(model_id: int, version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """通过 model_id 获取模型信息
    
    如果未指定 version_id，返回最新版本
    
    Returns:
        同 fetch_model_info_by_version
    """
    # 记录请求上下文
    _log_request_context()
    
    headers = {"Content-Type": "application/json"}
    token = get_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        response = requests.get(
            f"https://civitai.com/api/v1/models/{model_id}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        
        # 查找指定版本或最新版本
        versions = data.get("modelVersions", [])
        if not versions:
            return None
        
        target_version = None
        if version_id:
            for v in versions:
                if v.get("id") == version_id:
                    target_version = v
                    break
            if not target_version:
                print_warning(f"未找到版本 {version_id}，使用最新版本")
                target_version = versions[0]
        else:
            target_version = versions[0]
        
        # 查找主文件
        primary_file = None
        for f in target_version.get("files", []):
            if f.get("primary", False):
                primary_file = f
                break
        
        if not primary_file and target_version.get("files"):
            primary_file = target_version["files"][0]
        
        if not primary_file:
            return None
        
        model_type_raw = data.get("type", "other").lower()
        base_model = target_version.get("baseModel", "unknown").replace(" ", "")
        
        # 提取文件哈希 (优先 SHA256)
        hashes = primary_file.get("hashes", {})
        sha256 = hashes.get("SHA256", "")
        
        # 提取触发词
        trigger_words = target_version.get("trainedWords", [])
        
        return {
            "filename": primary_file.get("name", ""),
            "download_url": primary_file.get("downloadUrl", ""),
            "model_type": model_type_raw,
            "comfy_type": CIVITAI_TYPE_MAP.get(model_type_raw, "other"),
            "base_model": base_model,
            "size_kb": primary_file.get("sizeKB", 0),
            # 新增的元数据字段
            "model_id": data.get("id"),
            "version_id": target_version.get("id"),
            "model_name": data.get("name", ""),
            "version_name": target_version.get("name", ""),
            "trigger_words": trigger_words if trigger_words else [],
            "sha256": sha256,
        }
        
    except requests.RequestException as e:
        print_warning(f"CivitAI API 请求失败: {e}")
        return None


def resolve_civitai_url(url: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """解析 CivitAI URL 并获取下载信息
    
    Returns:
        (download_url, model_info) 或 (None, None)
    """
    parsed = parse_civitai_url(url)
    
    if not parsed["is_civitai"]:
        return None, None
    
    # 如果是 API 下载链接且有 version_id
    if parsed["is_api_url"] and parsed["version_id"]:
        info = fetch_model_info_by_version(parsed["version_id"])
        if info:
            return info["download_url"], info
    
    # 如果是模型页面
    if parsed["is_model_page"] and parsed["model_id"]:
        info = fetch_model_info(parsed["model_id"], parsed["version_id"])
        if info:
            return info["download_url"], info
    
    return None, None
