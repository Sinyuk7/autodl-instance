"""
下载前只读预检。

目标是尽早发现明显的磁盘空间不足；远端大小不可判断时只给 warning，
不阻断下载流程。
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.core.schema import EnvKey


ENV_HF_TOKEN = EnvKey.HF_TOKEN


@dataclass(frozen=True)
class PreflightResult:
    """下载预检结果。"""

    ok: bool
    known_size: bool
    size_bytes: Optional[int]
    free_bytes: int
    required_bytes: Optional[int]
    message: str
    next_step: Optional[str] = None


def _format_bytes(size: Optional[int]) -> str:
    if size is None:
        return "未知"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.2f} GB"


def _nearest_existing_parent(path: Path) -> Path:
    current = path.parent if path.suffix else path
    while not current.exists():
        parent = current.parent
        if parent == current:
            return parent
        current = parent
    return current


def _rewrite_huggingface_url(url: str) -> str:
    hf_endpoint = os.environ.get("HF_ENDPOINT", "")
    if "huggingface.co" in url and hf_endpoint and "huggingface.co" not in hf_endpoint:
        return url.replace("https://huggingface.co", hf_endpoint.rstrip("/"))
    return url


def _is_huggingface_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "huggingface.co" or host.endswith(".huggingface.co"):
        return True

    hf_endpoint = os.environ.get("HF_ENDPOINT", "")
    if hf_endpoint:
        mirror = urlparse(hf_endpoint)
        mirror_host = (mirror.hostname or "").lower()
        if mirror_host and (host == mirror_host or host.endswith(f".{mirror_host}")):
            return True
    return False


def _headers_for_url(url: str) -> dict[str, str]:
    headers = {"User-Agent": "autodl-instance/1.0"}
    if _is_huggingface_url(url):
        hf_token = os.environ.get(ENV_HF_TOKEN)
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
    return headers


def _content_length(headers: object) -> Optional[int]:
    value = headers.get("Content-Length") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        parsed = int(str(value))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _content_range_total(headers: object) -> Optional[int]:
    value = headers.get("Content-Range") if hasattr(headers, "get") else None
    if not value:
        return None
    match = re.search(r"/(\d+)$", str(value))
    if not match:
        return None
    try:
        parsed = int(match.group(1))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def estimate_remote_size(url: str, timeout: int = 10) -> Optional[int]:
    """估算远端文件大小。

    先用 HEAD；服务端不支持 HEAD 时再用 Range GET 探测 1 byte。
    任何网络/鉴权/解析失败都返回 None，由调用方决定是否继续下载。
    """
    request_url = _rewrite_huggingface_url(url)
    headers = _headers_for_url(request_url)

    try:
        request = Request(request_url, headers=headers, method="HEAD")
        with urlopen(request, timeout=timeout) as response:
            return _content_length(response.headers)
    except HTTPError as exc:
        if exc.code not in {400, 403, 405, 501}:
            return None
    except (OSError, URLError, ValueError):
        return None

    range_headers = dict(headers)
    range_headers["Range"] = "bytes=0-0"
    try:
        request = Request(request_url, headers=range_headers, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return _content_range_total(response.headers) or _content_length(response.headers)
    except (HTTPError, OSError, URLError, ValueError):
        return None


def check_disk_space(target_path: Path, expected_size_bytes: Optional[int]) -> PreflightResult:
    """检查目标路径所在磁盘是否有足够空间。

    不创建目录；如果已有部分文件，按剩余需要写入的字节数计算。
    """
    usage_root = _nearest_existing_parent(target_path)
    free_bytes = shutil.disk_usage(usage_root).free

    if expected_size_bytes is None:
        return PreflightResult(
            ok=True,
            known_size=False,
            size_bytes=None,
            free_bytes=free_bytes,
            required_bytes=None,
            message=(
                f"无法预估远端文件大小；目标磁盘剩余 {_format_bytes(free_bytes)}，"
                "将继续下载。"
            ),
            next_step="如果下载失败或中断，先执行 doctor 查看数据盘空间。",
        )

    existing_bytes = target_path.stat().st_size if target_path.exists() else 0
    required_bytes = max(expected_size_bytes - existing_bytes, 0)

    if free_bytes < required_bytes:
        return PreflightResult(
            ok=False,
            known_size=True,
            size_bytes=expected_size_bytes,
            free_bytes=free_bytes,
            required_bytes=required_bytes,
            message=(
                f"磁盘空间不足：目标文件约 {_format_bytes(expected_size_bytes)}，"
                f"仍需写入 {_format_bytes(required_bytes)}，"
                f"当前仅剩 {_format_bytes(free_bytes)}。"
            ),
            next_step=(
                "清理 /root/autodl-tmp 后重试，或更换更大数据盘；"
                "可先执行 doctor 查看空间占用。"
            ),
        )

    return PreflightResult(
        ok=True,
        known_size=True,
        size_bytes=expected_size_bytes,
        free_bytes=free_bytes,
        required_bytes=required_bytes,
        message=(
            f"磁盘预检通过：目标文件约 {_format_bytes(expected_size_bytes)}，"
            f"仍需写入 {_format_bytes(required_bytes)}，"
            f"当前剩余 {_format_bytes(free_bytes)}。"
        ),
    )


def prepare_download_preflight(
    url: str,
    target_path: Path,
    known_size_bytes: Optional[int] = None,
) -> PreflightResult:
    """下载前预检入口。"""
    expected_size = known_size_bytes
    if expected_size is None:
        expected_size = estimate_remote_size(url)
    return check_disk_space(target_path, expected_size)
