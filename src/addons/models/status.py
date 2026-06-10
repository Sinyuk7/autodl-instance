"""
Read-only model lock status helpers.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.addons.models.config import LOCK_FILE, get_models_base
from src.lib.utils import load_yaml, sha256


def _first_model_path(model: Dict[str, Any]) -> str:
    return model.get("paths", [{}])[0].get("path", "")


def _expected_hash(model: Dict[str, Any]) -> str:
    return model.get("hashes", [{}])[0].get("hash", "")


def collect_lock_status(
    lock_file: Path = LOCK_FILE,
    models_base: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """对比 lock 与本地模型目录，返回三态状态列表。"""
    lock = load_yaml(lock_file)
    models = lock.get("models", [])
    base = models_base or get_models_base()

    results: List[Dict[str, str]] = []
    for model in models:
        name = model.get("model", "?")
        model_type = model.get("type", "?")
        rel_path = _first_model_path(model)
        url = model.get("url", "")
        target = base / rel_path if rel_path else None

        status = "缺失"
        detail = "lock 中有记录，但本地文件不存在"
        if target and target.exists():
            expected = _expected_hash(model)
            if expected:
                try:
                    actual = sha256(target)
                    if actual == expected:
                        status = "存在"
                        detail = "文件存在，hash 一致"
                    else:
                        status = "漂移"
                        detail = "文件存在，但 hash 与 lock 不一致"
                except OSError as e:
                    status = "漂移"
                    detail = f"无法读取文件计算 hash: {e}"
            else:
                status = "存在"
                detail = "文件存在，lock 未记录 hash"

        results.append({
            "status": status,
            "name": str(name),
            "type": str(model_type),
            "path": rel_path,
            "url": str(url),
            "detail": detail,
        })

    return results
