"""
HuggingFace Hub 嵌套路径下载测试

覆盖 hf_hub.py 中 filename 含子路径时的临时目录（staging）逻辑，
以及 post_download / on_interrupt 中嵌套空目录的清理。
"""
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# huggingface_hub 可能未安装，注入 mock 模块以便测试
_hf_mock = MagicMock()
sys.modules.setdefault("huggingface_hub", _hf_mock)

from src.lib.download.hf_hub import HuggingFaceHubStrategy


class TestNestedPathDownload:
    """filename 含 "/" 时的 staging download 逻辑"""

    @pytest.fixture
    def strategy(self) -> HuggingFaceHubStrategy:
        s = HuggingFaceHubStrategy()
        s._enabled = True
        return s

    def test_simple_filename_downloads_in_place(self, strategy, tmp_path: Path):
        """简单文件名直接下载到 target_path.parent"""
        target = tmp_path / "unet" / "model.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)

        parsed = ("org/repo", "model.safetensors", None, None)

        def fake_hf_download(**kwargs):
            # 模拟 hf_hub_download：在 local_dir 下创建文件
            out = Path(kwargs["local_dir"]) / kwargs["filename"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"model-data")
            return str(out)

        _hf_mock.hf_hub_download = MagicMock(side_effect=fake_hf_download)
        with patch("src.lib.download.hf_hub.parse_hf_url", return_value=parsed):
            result = strategy.download(
                "https://hf.co/org/repo/resolve/main/model.safetensors",
                target,
            )

        assert target.exists()
        assert target.read_bytes() == b"model-data"
        # 不应在 target 同级出现 staging 残留目录
        assert not any(d.name.startswith("hf_dl_") for d in tmp_path.rglob("*") if d.is_dir())

    def test_nested_filename_uses_staging(self, strategy, tmp_path: Path):
        """含子路径的 filename 使用临时目录，最终文件正确移到 target"""
        target = tmp_path / "clip" / "qwen.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)

        nested_filename = "split_files/text_encoders/qwen.safetensors"
        parsed = ("Comfy-Org/z_image", nested_filename, "main", None)

        def fake_hf_download(**kwargs):
            # hf_hub_download 会在 local_dir 下按 filename 的路径结构创建文件
            out = Path(kwargs["local_dir"]) / kwargs["filename"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"nested-model")
            return str(out)

        _hf_mock.hf_hub_download = MagicMock(side_effect=fake_hf_download)
        with patch("src.lib.download.hf_hub.parse_hf_url", return_value=parsed):
            result = strategy.download(
                "https://hf.co/Comfy-Org/z_image/resolve/main/split_files/text_encoders/qwen.safetensors",
                target,
            )

        # 文件到达最终位置
        assert target.exists()
        assert target.read_bytes() == b"nested-model"
        # target 的父目录下不应有 split_files 这种嵌套残留
        assert not (target.parent / "split_files").exists()

    def test_staging_cleaned_on_error(self, strategy, tmp_path: Path):
        """下载失败时异常冒泡，但临时目录仍被 finally 清理"""
        target = tmp_path / "clip" / "fail.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)

        parsed = ("org/repo", "sub/dir/fail.safetensors", None, None)
        staging_dirs_before = set(Path("/tmp").glob("hf_dl_*"))

        def fake_hf_download_fail(**kwargs):
            # 记录 staging 目录路径，供后续验证清理
            self._staging_dir = Path(kwargs["local_dir"])
            out = self._staging_dir / kwargs["filename"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"partial")
            raise RuntimeError("download failed")

        _hf_mock.hf_hub_download = MagicMock(side_effect=fake_hf_download_fail)
        with patch("src.lib.download.hf_hub.parse_hf_url", return_value=parsed):
            with pytest.raises(RuntimeError, match="download failed"):
                strategy.download(
                    "https://hf.co/org/repo/resolve/main/sub/dir/fail.safetensors",
                    target,
                )

        # 临时 staging 目录应被 finally 清理
        assert not self._staging_dir.exists()
        assert not target.exists()


class TestCleanupNestedDirs:
    """post_download / on_interrupt 中清理嵌套空目录"""

    @pytest.fixture
    def strategy(self) -> HuggingFaceHubStrategy:
        s = HuggingFaceHubStrategy()
        s._enabled = True
        return s

    def test_post_download_removes_empty_nested(self, strategy, tmp_path: Path):
        """post_download 清理 filename 子路径产生的空目录"""
        target = tmp_path / "models" / "file.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        # 模拟 hf_hub_download 产生的嵌套空目录
        nested = target.parent / "split_files" / "text_encoders"
        nested.mkdir(parents=True)

        strategy._current_filename = "split_files/text_encoders/file.safetensors"
        strategy.post_download(target)

        assert not (target.parent / "split_files").exists()

    def test_post_download_keeps_non_empty_dirs(self, strategy, tmp_path: Path):
        """post_download 不删除含文件的目录"""
        target = tmp_path / "models" / "file.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        nested = target.parent / "split_files"
        nested.mkdir()
        (nested / "important.txt").write_text("keep me")

        strategy._current_filename = "split_files/something.safetensors"
        strategy.post_download(target)

        assert nested.exists()
        assert (nested / "important.txt").exists()

    def test_on_interrupt_cleans_nested(self, strategy, tmp_path: Path):
        """on_interrupt 也会清理嵌套空目录"""
        target = tmp_path / "models" / "file.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)

        nested = target.parent / "sub_path" / "deep"
        nested.mkdir(parents=True)

        strategy._current_filename = "sub_path/deep/file.safetensors"
        strategy.on_interrupt(target)

        assert not (target.parent / "sub_path").exists()

    def test_no_cleanup_for_simple_filename(self, strategy, tmp_path: Path):
        """简单 filename（无 /）不触发嵌套清理"""
        target = tmp_path / "models" / "file.safetensors"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        strategy._current_filename = "file.safetensors"
        strategy.post_download(target)

        # 无副作用，target 目录内容不变
        assert target.exists()
