from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

from src.lib.download import preflight


def _disk_usage(free: int):
    return SimpleNamespace(total=free * 2, used=free, free=free)


class _Response:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_check_disk_space_known_size_fits(tmp_path: Path, monkeypatch):
    target = tmp_path / "models" / "model.safetensors"
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: _disk_usage(20_000))

    result = preflight.check_disk_space(target, 10_000)

    assert result.ok is True
    assert result.known_size is True
    assert result.size_bytes == 10_000
    assert result.required_bytes == 10_000
    assert result.free_bytes == 20_000


def test_check_disk_space_known_size_insufficient(tmp_path: Path, monkeypatch):
    target = tmp_path / "models" / "model.safetensors"
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: _disk_usage(5_000))

    result = preflight.check_disk_space(target, 10_000)

    assert result.ok is False
    assert result.known_size is True
    assert result.required_bytes == 10_000
    assert "磁盘空间不足" in result.message
    assert result.next_step


def test_check_disk_space_existing_partial_reduces_required(tmp_path: Path, monkeypatch):
    target = tmp_path / "model.safetensors"
    target.write_bytes(b"x" * 6_000)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: _disk_usage(5_000))

    result = preflight.check_disk_space(target, 10_000)

    assert result.ok is True
    assert result.required_bytes == 4_000
    assert result.free_bytes == 5_000


def test_check_disk_space_unknown_size_warns_but_allows(tmp_path: Path, monkeypatch):
    target = tmp_path / "models" / "model.safetensors"
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: _disk_usage(1_000))

    result = preflight.check_disk_space(target, None)

    assert result.ok is True
    assert result.known_size is False
    assert result.size_bytes is None
    assert result.required_bytes is None
    assert result.next_step


def test_estimate_remote_size_reads_content_length(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout):
        seen.append((request, timeout))
        return _Response({"Content-Length": "12345"})

    monkeypatch.setattr(preflight, "urlopen", fake_urlopen)

    assert preflight.estimate_remote_size("https://example.com/model.bin", timeout=3) == 12345
    request, timeout = seen[0]
    assert request.get_method() == "HEAD"
    assert timeout == 3


def test_estimate_remote_size_falls_back_to_range_get(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.get_method())
        if request.get_method() == "HEAD":
            raise HTTPError(request.full_url, 405, "method not allowed", {}, None)
        return _Response({"Content-Range": "bytes 0-0/98765"})

    monkeypatch.setattr(preflight, "urlopen", fake_urlopen)

    assert preflight.estimate_remote_size("https://example.com/model.bin") == 98765
    assert calls == ["HEAD", "GET"]


def test_estimate_remote_size_returns_none_on_network_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(preflight, "urlopen", fake_urlopen)

    assert preflight.estimate_remote_size("https://example.com/model.bin") is None


def test_estimate_remote_size_uses_hf_mirror_and_token(monkeypatch):
    seen = []
    monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.example")
    monkeypatch.setenv("HF_TOKEN", "secret-token")

    def fake_urlopen(request, timeout):
        seen.append(request)
        return _Response({"Content-Length": "42"})

    monkeypatch.setattr(preflight, "urlopen", fake_urlopen)

    size = preflight.estimate_remote_size(
        "https://huggingface.co/org/repo/resolve/main/model.safetensors"
    )

    assert size == 42
    request = seen[0]
    assert request.full_url.startswith("https://hf-mirror.example/")
    assert request.headers["Authorization"] == "Bearer secret-token"
