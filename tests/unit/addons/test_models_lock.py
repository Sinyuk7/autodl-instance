"""
Models Lock 单元测试

覆盖 lock.py 的公开接口：scan_models / generate_snapshot / read_meta / write_meta / cleanup_orphan_metas
"""
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from src.addons.models.lock import (
    EXCLUDED_EXTENSIONS,
    scan_models,
    generate_snapshot,
    read_meta,
    write_meta,
    cleanup_orphan_metas,
)


# ── helpers ──────────────────────────────────────────────────

def _create_model(base: Path, rel_path: str, content: bytes = b"fake-model") -> Path:
    """在 base 下创建模型文件并返回绝对路径"""
    p = base / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _create_meta(base: Path, model_rel: str, meta: Dict[str, Any]) -> Path:
    """为模型文件创建 .meta sidecar"""
    model_path = base / model_rel
    write_meta(model_path, meta)
    from src.addons.models.lock import _meta_path_for
    return _meta_path_for(model_path)


# ── scan_models ──────────────────────────────────────────────

class TestScanModels:
    """scan_models 扫描逻辑"""

    def test_empty_directory(self, tmp_path: Path):
        """空目录返回空列表"""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        assert scan_models(models_dir) == []

    def test_nonexistent_directory(self, tmp_path: Path):
        """不存在的目录返回空列表"""
        assert scan_models(tmp_path / "no_such_dir") == []

    def test_scans_model_files_with_type(self, tmp_path: Path):
        """正常扫描：返回 path/size/type，type 为第一层子目录"""
        models = tmp_path / "models"
        _create_model(models, "unet/flux.safetensors", b"A" * 100)
        _create_model(models, "clip/clip_l.safetensors", b"B" * 50)

        result = scan_models(models)
        paths = {r["path"] for r in result}

        assert paths == {"unet/flux.safetensors", "clip/clip_l.safetensors"}
        # type = 第一层目录名
        by_path = {r["path"]: r for r in result}
        assert by_path["unet/flux.safetensors"]["type"] == "unet"
        assert by_path["unet/flux.safetensors"]["size"] == 100

    def test_root_level_file_has_no_type(self, tmp_path: Path):
        """根目录直接的文件 type 为 None"""
        models = tmp_path / "models"
        _create_model(models, "standalone.ckpt")

        result = scan_models(models)
        assert len(result) == 1
        assert result[0]["type"] is None

    @pytest.mark.parametrize("ext", [".yaml", ".json", ".txt", ".png", ".zip", ".meta", ".py"])
    def test_excludes_non_model_extensions(self, tmp_path: Path, ext: str):
        """排除列表中的扩展名不会被扫描"""
        models = tmp_path / "models"
        _create_model(models, f"unet/file{ext}")
        assert scan_models(models) == []

    def test_includes_unknown_extensions(self, tmp_path: Path):
        """不在排除列表中的扩展名（如 .gguf .onnx）可被扫描"""
        models = tmp_path / "models"
        _create_model(models, "unet/model.gguf")
        _create_model(models, "unet/model.onnx")

        paths = {r["path"] for r in scan_models(models)}
        assert "unet/model.gguf" in paths
        assert "unet/model.onnx" in paths

    def test_hidden_files_are_skipped(self, tmp_path: Path):
        """隐藏文件（.开头）被跳过"""
        models = tmp_path / "models"
        _create_model(models, "unet/.hidden_model.safetensors")
        _create_model(models, "unet/visible.safetensors")

        result = scan_models(models)
        assert len(result) == 1
        assert result[0]["path"] == "unet/visible.safetensors"

    def test_merges_meta_sidecar(self, tmp_path: Path):
        """存在 .meta sidecar 时，合并 url/model/source 到扫描结果"""
        models = tmp_path / "models"
        _create_model(models, "unet/flux.safetensors")
        _create_meta(models, "unet/flux.safetensors", {
            "url": "https://hf.co/repo/flux.safetensors",
            "model": "FLUX",
            "source": "hf_hub",
        })

        result = scan_models(models)
        assert len(result) == 1
        entry = result[0]
        assert entry["url"] == "https://hf.co/repo/flux.safetensors"
        assert entry["model"] == "FLUX"
        assert entry["source"] == "hf_hub"


# ── generate_snapshot ────────────────────────────────────────

class TestGenerateSnapshot:
    """generate_snapshot 快照生成 + 增量 hash"""

    def test_basic_snapshot(self, tmp_path: Path):
        """基本快照：包含 generated_at 和 models 列表"""
        models = tmp_path / "models"
        _create_model(models, "unet/test.safetensors", b"hello")

        snap = generate_snapshot(models, {})

        assert "generated_at" in snap
        assert len(snap["models"]) == 1

        m = snap["models"][0]
        assert m["paths"] == [{"path": "unet/test.safetensors"}]
        assert m["hashes"][0]["type"] == "SHA256"
        assert len(m["hashes"][0]["hash"]) == 64  # SHA256 hex
        assert m["type"] == "unet"
        assert m["_size"] == 5  # len(b"hello")

    def test_incremental_hash_reuse(self, tmp_path: Path):
        """文件 size+mtime 未变时，复用上一次 hash，不重新计算"""
        models = tmp_path / "models"
        model_file = _create_model(models, "unet/big.safetensors", b"X" * 1000)

        # 第一次快照
        snap1 = generate_snapshot(models, {})
        hash1 = snap1["models"][0]["hashes"][0]["hash"]

        # 第二次快照，传入 snap1 作为 previous_lock
        snap2 = generate_snapshot(models, snap1)
        hash2 = snap2["models"][0]["hashes"][0]["hash"]

        assert hash1 == hash2  # hash 应一致（复用）

    def test_incremental_hash_recalc_on_change(self, tmp_path: Path):
        """文件内容变更后（size 不同），重新计算 hash"""
        models = tmp_path / "models"
        model_file = _create_model(models, "unet/model.safetensors", b"v1")

        snap1 = generate_snapshot(models, {})
        hash1 = snap1["models"][0]["hashes"][0]["hash"]

        # 修改文件内容（size 变化）
        time.sleep(0.05)  # 确保 mtime 变化
        model_file.write_bytes(b"version2-longer")

        snap2 = generate_snapshot(models, snap1)
        hash2 = snap2["models"][0]["hashes"][0]["hash"]

        assert hash1 != hash2

    def test_deleted_file_not_in_snapshot(self, tmp_path: Path):
        """删除文件后，快照不再包含该文件"""
        models = tmp_path / "models"
        f = _create_model(models, "unet/to_delete.safetensors")

        snap1 = generate_snapshot(models, {})
        assert len(snap1["models"]) == 1

        f.unlink()

        snap2 = generate_snapshot(models, snap1)
        assert len(snap2["models"]) == 0

    def test_model_name_from_meta(self, tmp_path: Path):
        """model 名优先从 .meta 获取"""
        models = tmp_path / "models"
        _create_model(models, "unet/abc123.safetensors")
        _create_meta(models, "unet/abc123.safetensors", {"model": "FLUX-dev"})

        snap = generate_snapshot(models, {})
        assert snap["models"][0]["model"] == "FLUX-dev"

    def test_model_name_fallback_to_stem(self, tmp_path: Path):
        """无 .meta 时 model 名回退到文件 stem"""
        models = tmp_path / "models"
        _create_model(models, "clip/clip_l.safetensors")

        snap = generate_snapshot(models, {})
        assert snap["models"][0]["model"] == "clip_l"


# ── read_meta / write_meta ───────────────────────────────────

class TestMetaSidecar:
    """read_meta / write_meta 读写"""

    def test_write_then_read(self, tmp_path: Path):
        """写入后读取，数据一致"""
        model = _create_model(tmp_path, "vae/vae.safetensors")
        meta = {"url": "https://example.com/vae.safetensors", "source": "aria2"}

        write_meta(model, meta)
        loaded = read_meta(model)

        assert loaded["url"] == meta["url"]
        assert loaded["source"] == meta["source"]

    def test_read_nonexistent_returns_empty(self, tmp_path: Path):
        """不存在 .meta 时返回空字典"""
        model = tmp_path / "clip" / "model.safetensors"
        model.parent.mkdir(parents=True)
        model.touch()
        assert read_meta(model) == {}

    def test_meta_path_is_hidden(self, tmp_path: Path):
        """sidecar 文件名以 . 开头（隐藏文件）"""
        model = _create_model(tmp_path, "unet/flux.safetensors")
        write_meta(model, {"url": "test"})

        meta_file = model.parent / ".flux.safetensors.meta"
        assert meta_file.exists()


# ── cleanup_orphan_metas ────────────────────────────────────

class TestCleanupOrphanMetas:
    """cleanup_orphan_metas 孤儿清理"""

    def test_removes_orphan_meta(self, tmp_path: Path):
        """模型文件不存在时，对应 .meta 被清理"""
        models = tmp_path / "models"
        model = _create_model(models, "unet/gone.safetensors")
        meta_file = _create_meta(models, "unet/gone.safetensors", {"url": "x"})

        # 删除模型文件，保留 .meta
        model.unlink()
        assert meta_file.exists()

        count = cleanup_orphan_metas(models)
        assert count == 1
        assert not meta_file.exists()

    def test_keeps_valid_meta(self, tmp_path: Path):
        """模型文件存在时，.meta 不被清理"""
        models = tmp_path / "models"
        _create_model(models, "unet/alive.safetensors")
        meta_file = _create_meta(models, "unet/alive.safetensors", {"url": "y"})

        count = cleanup_orphan_metas(models)
        assert count == 0
        assert meta_file.exists()

    def test_nonexistent_dir(self, tmp_path: Path):
        """目录不存在时返回 0"""
        assert cleanup_orphan_metas(tmp_path / "no_dir") == 0
