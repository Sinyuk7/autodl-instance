"""
Lock 文件管理

管理 model-lock.yaml 模型快照。
快照在 sync 时通过扫描 shared_models 目录生成，
记录当前所有模型文件的路径、哈希、类型及来源信息。
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.lib.utils import load_yaml, save_yaml, sha256
from src.core.utils import logger

# 排除的文件扩展名（非模型文件）
EXCLUDED_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".txt", ".md", ".log",
    ".py", ".sh", ".bat", ".ps1",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
    ".html", ".css", ".js",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".lock", ".metadata",  # 下载缓存的锁文件和元数据
    ".meta",  # sidecar 元数据文件
}

# Meta sidecar 后缀
META_SUFFIX = ".meta"


def _meta_path_for(model_path: Path) -> Path:
    """获取模型文件对应的 .meta sidecar 路径

    例: unet/flux.safetensors -> unet/.flux.safetensors.meta
    """
    return model_path.parent / f".{model_path.name}{META_SUFFIX}"


def read_meta(model_path: Path) -> Dict[str, Any]:
    """读取模型文件对应的 .meta sidecar

    Returns:
        meta 数据字典，不存在则返回空字典
    """
    meta_file = _meta_path_for(model_path)
    if meta_file.exists():
        return load_yaml(meta_file)
    return {}


def write_meta(model_path: Path, meta: Dict[str, Any]) -> None:
    """写入模型文件对应的 .meta sidecar"""
    meta_file = _meta_path_for(model_path)
    save_yaml(meta_file, meta)


def scan_models(models_base: Path) -> List[Dict[str, Any]]:
    """扫描 shared_models 目录下的所有模型文件

    递归扫描 models_base 下所有子目录，收集模型文件信息。

    Args:
        models_base: 模型根目录 (shared_models/)

    Returns:
        模型文件信息列表 (不含 hash，hash 由 generate_snapshot 增量计算)
    """
    results: List[Dict[str, Any]] = []

    if not models_base.exists():
        return results

    for model_file in sorted(models_base.rglob("*")):
        if not model_file.is_file():
            continue
        # 跳过隐藏文件 (如 .meta sidecar)
        if model_file.name.startswith("."):
            continue
        # 跳过隐藏目录下的文件 (如 .cache/)
        rel_parts = model_file.relative_to(models_base).parts
        if any(part.startswith(".") for part in rel_parts[:-1]):
            continue
        # 跳过已知的非模型文件
        if model_file.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue

        rel_path = str(model_file.relative_to(models_base))
        # type = 第一层子目录名
        parts = rel_path.split("/")
        model_type = parts[0] if len(parts) > 1 else None

        stat = model_file.stat()

        entry: Dict[str, Any] = {
            "path": rel_path,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "type": model_type,
        }

        # 合并 .meta sidecar 信息
        meta = read_meta(model_file)
        if meta:
            if meta.get("url"):
                entry["url"] = meta["url"]
            if meta.get("model"):
                entry["model"] = meta["model"]
            if meta.get("source"):
                entry["source"] = meta["source"]

        results.append(entry)

    return results


def generate_snapshot(
    models_base: Path,
    previous_lock: Dict[str, Any],
) -> Dict[str, Any]:
    """生成模型目录快照

    扫描 models_base 下所有模型文件，增量计算 hash（仅新增/修改的文件）。

    Args:
        models_base: 模型根目录
        previous_lock: 上一次 lock 数据（用于增量 hash 判断）

    Returns:
        完整的 lock 数据字典
    """
    # 构建上一次 lock 的索引: path -> entry
    prev_index: Dict[str, Dict[str, Any]] = {}
    for m in previous_lock.get("models", []):
        path = m.get("paths", [{}])[0].get("path", "")
        if path:
            prev_index[path] = m

    # 扫描当前文件
    scanned = scan_models(models_base)

    models: List[Dict[str, Any]] = []
    for item in scanned:
        rel_path = item["path"]
        file_path = models_base / rel_path

        # 增量 hash: 如果上一次 lock 中有此文件且 size+mtime 未变，复用 hash
        prev = prev_index.get(rel_path)
        existing_hash: Optional[str] = None

        if prev:
            prev_hashes = prev.get("hashes", [])
            if prev_hashes:
                existing_hash = prev_hashes[0].get("hash")
            # 检查是否需要重新计算
            prev_size = prev.get("_size")
            prev_mtime = prev.get("_mtime")
            if prev_size == item["size"] and prev_mtime == item["mtime"] and existing_hash:
                file_hash = existing_hash
            else:
                logger.info(f"  -> 计算 hash: {rel_path}")
                file_hash = sha256(file_path)
        else:
            logger.info(f"  -> 计算 hash (新文件): {rel_path}")
            file_hash = sha256(file_path)

        # 构造 lock entry (保持与原格式一致)
        entry: Dict[str, Any] = {}

        # model name: 优先从 meta 获取，否则用文件 stem
        entry["model"] = item.get("model", file_path.stem)

        # url: 可选，来自 meta
        if item.get("url"):
            entry["url"] = item["url"]

        entry["paths"] = [{"path": rel_path}]
        entry["hashes"] = [{"hash": file_hash, "type": "SHA256"}]

        # type: 可选标签
        if item.get("type"):
            entry["type"] = item["type"]

        # 内部字段：用于下次增量判断 (以 _ 开头表示内部使用)
        entry["_size"] = item["size"]
        entry["_mtime"] = item["mtime"]

        models.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }


def cleanup_orphan_metas(models_base: Path) -> int:
    """清理孤儿 .meta 文件

    扫描 models_base 下所有 .meta 文件，
    如果对应的模型文件不存在，则删除该 .meta。

    Returns:
        删除的孤儿 .meta 数量
    """
    cleaned = 0

    if not models_base.exists():
        return cleaned

    for meta_file in models_base.rglob(f".*{META_SUFFIX}"):
        if not meta_file.is_file():
            continue

        # .flux.safetensors.meta -> flux.safetensors
        model_name = meta_file.name[1:]  # 去掉开头的 .
        if model_name.endswith(META_SUFFIX):
            model_name = model_name[:-len(META_SUFFIX)]

        model_file = meta_file.parent / model_name
        if not model_file.exists():
            try:
                meta_file.unlink()
                logger.info(f"  -> 清理孤儿 meta: {meta_file.name}")
                cleaned += 1
            except OSError:
                pass

    return cleaned


