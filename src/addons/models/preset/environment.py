"""Host checks and one-time ComfyUI search-path configuration."""
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

import requests
import yaml

from src.core.adapters import SubprocessRunner
from src.core.runtime import DEFAULT_CONFIG_FILE, load_local_config
from .copy import ALIASES, CATEGORIES, safe_path


@dataclass
class Settings:
    source: Path
    root: Path
    presets: Path
    comfy: Path
    port: int = 6006

    @classmethod
    def load(cls, config_file=DEFAULT_CONFIG_FILE):
        # Do not initialize networking or read secrets for model inspection.
        config = load_local_config(config_file)

        def path(key, default, alias=None):
            value = os.environ.get("AUTODL_" + key.upper())
            if alias:
                value = value or os.environ.get(alias)
            return Path(os.path.expandvars(str(value or config.get(key) or default))).expanduser().absolute()

        base = path("base_dir", "/root/autodl-tmp")
        port = int(config.get("model_port", 6006))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid model_port")
        return cls(path("models_dir", "/root/autodl-fs/models", "COMFYUI_MODELS_DIR"),
                   path("local_models_dir", base / "ComfyUI/models"),
                   path("model_presets_dir", Path(config_file).parent / "presets"),
                   path("comfy_dir", "/root/ComfyUI"), port)


def _check_storage_mount(root, target, runner):
    # AutoDL can expose its real network mount through /root/autodl-fs.
    # Compare resolved paths and validate the mount itself, not the alias.
    mounted_root = root.resolve()
    if not target.resolve().is_relative_to(mounted_root):
        raise RuntimeError(f"Expected storage below {root}: {target}")
    for command in (["findmnt", "-T", str(mounted_root)],
                    ["mountpoint", "-q", str(mounted_root)],
                    ["df", "-hT", str(mounted_root)], ["df", "-i", str(mounted_root)]):
        result = runner.run(command, check=False, timeout=10)
        if result.returncode:
            raise RuntimeError(f"Storage check failed: {' '.join(command)}")
    if not mounted_root.is_mount():
        raise RuntimeError(f"Storage is not mounted: {root} -> {mounted_root}")


def check_storage(settings, runner=None):
    """Require real AutoDL mounts; inspect capacity/inodes before storage writes."""
    runner = runner or SubprocessRunner()
    for root, target in ((Path("/root/autodl-fs"), settings.source),
                         (Path("/root/autodl-tmp"), settings.root)):
        _check_storage_mount(root, target, runner)
    if not settings.source.is_dir():
        raise RuntimeError(f"Shared model root missing: {settings.source}")
    safe_path(settings.root, "")
    ancestor = settings.root
    while not ancestor.exists():
        ancestor = ancestor.parent
    fs = os.statvfs(ancestor)
    if fs.f_favail == 0 or fs.f_bavail == 0:
        raise RuntimeError("Local disk has no free blocks or inodes")


def groups():
    result = {}
    for name in sorted(CATEGORIES):
        result.setdefault(ALIASES.get(name, name), []).append(name)
    return result


def blocks(settings):
    mapping = {key: "\n".join(reversed(values)) for key, values in groups().items()}
    fallback = {key: "\n".join(values) for key, values in groups().items()}
    # Each is_default registration prepends, hence reversed alias order in YAML.
    return {
        "autodl_canonical_models": {"base_path": str(settings.source), **fallback},
        "autodl_local_models": {"base_path": str(settings.root),
                                     "is_default": True, **mapping},
    }


def configuration_ready(settings):
    path = settings.comfy / "extra_model_paths.yaml"
    if not path.is_file():
        return False
    data = yaml.safe_load(path.read_text())
    expected = blocks(settings)
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items()):
        return False
    # Later default blocks can prepend over local models. Do not silently assume priority.
    keys = list(data)
    return keys[-1:] == ["autodl_local_models"]


def configure(settings):
    """Append owned YAML blocks without changing existing links or user comments."""
    settings.comfy.mkdir(parents=True, exist_ok=True)
    path = settings.comfy / "extra_model_paths.yaml"
    if path.is_symlink():
        raise RuntimeError("Refusing to replace a symlinked extra_model_paths.yaml")
    original = path.read_text() if path.exists() else ""
    data = yaml.safe_load(original) or {}
    if not isinstance(data, dict):
        raise ValueError("extra_model_paths.yaml must be a mapping")
    expected = blocks(settings)
    if configuration_ready(settings):
        return {"configured": True, "changed": False}
    # Upgrade only the exact previous generated suffix, preserving user text.
    old_blocks = {
        "autodl_canonical_models": {**expected["autodl_local_models"],
                                    "base_path": str(settings.source)},
        "autodl_local_models": expected["autodl_local_models"],
    }
    prefix, separator, suffix = original.rpartition("# AutoDL model paths (managed)")
    if (separator and yaml.safe_load(suffix) == old_blocks
            and all(data.get(k) == v for k, v in old_blocks.items())):
        original = prefix
        data = yaml.safe_load(original) or {}
    legacy_keys = ("autodl_canonical_models", "autodl_local_model_cache")
    marker = "# AutoDL local model cache (managed)"
    if "autodl_local_model_cache" in data:
        prefix, separator, suffix = original.rpartition(marker)
        legacy = yaml.safe_load(suffix) if separator else None
        if (not separator or not isinstance(legacy, dict) or tuple(legacy) != legacy_keys
                or any(data[k] != legacy[k] for k in legacy_keys)):
            raise RuntimeError("Legacy model paths were modified; review manually")
        if Path(legacy["autodl_local_model_cache"].get("base_path", "")).name != "cache":
            raise RuntimeError("Unexpected legacy model directory; review manually")
        original = prefix
        data = yaml.safe_load(original) or {}
    if any(key in data for key in expected):
        raise RuntimeError("Managed resolver blocks differ or are not last; review configuration manually")
    # Explicit YAML document terminators would cause appended blocks to be ignored.
    if any(line.strip() in ("---", "...") for line in original.splitlines()):
        raise ValueError("Explicit YAML document markers require manual configuration")
    content = original.rstrip() + "\n\n# AutoDL model paths (managed)\n" + yaml.safe_dump(expected, sort_keys=False)
    if yaml.safe_load(content) != {**data, **expected}:
        raise ValueError("Cannot safely append resolver configuration")
    with tempfile.NamedTemporaryFile(mode="w", dir=settings.comfy, prefix=".model-paths-", delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.chmod(tmp, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return {"configured": True, "changed": True,
            "note": "Restart ComfyUI when convenient to load paths; no automatic restart performed."}


def probe(settings):
    """Query only loopback, bypassing shell proxies; never return queue payloads."""
    with requests.Session() as session:
        session.trust_env = False
        try:
            response = session.get(f"http://127.0.0.1:{settings.port}/queue", timeout=3,
                                   allow_redirects=False)
            response.raise_for_status()
            queue = response.json()
            if not isinstance(queue, dict) or any(not isinstance(queue.get(k), list)
                                                   for k in ("queue_running", "queue_pending")):
                raise ValueError("Invalid queue response")
        except (requests.RequestException, ValueError):
            # A failed HTTP check does not establish that ComfyUI is stopped.
            # Inspect only process entrypoints, never print command lines/secrets.
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                try:
                    args = (proc / "cmdline").read_bytes().split(b"\0")
                    if any(b"main.py" in arg or b"comfy" in arg.lower() for arg in args[:3]):
                        return {"state": "UNVERIFIED", "paths": None}
                except FileNotFoundError:
                    continue
                except PermissionError:
                    return {"state": "UNVERIFIED", "paths": None}
            # Check for an occupied but unresponsive endpoint as well.
            import socket
            with socket.socket() as sock:
                sock.settimeout(1)
                if sock.connect_ex(("127.0.0.1", settings.port)) == 0:
                    return {"state": "UNVERIFIED", "paths": None}
            return {"state": "STOPPED", "paths": None}
        state = "BUSY" if queue["queue_running"] or queue["queue_pending"] else "IDLE"
        try:
            response = session.get(f"http://127.0.0.1:{settings.port}/internal/folder_paths", timeout=3,
                                   allow_redirects=False)
            response.raise_for_status()
            paths = response.json()
            if not isinstance(paths, dict) or any(not isinstance(v, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in v) for v in paths.values()):
                raise ValueError("Invalid folder paths response")
        except (requests.RequestException, ValueError):
            paths = None
        return {"state": state, "paths": paths}


def priority_ready(settings, paths):
    if paths is None:
        return False
    for key, categories in groups().items():
        actual = [Path(p).resolve() for p in paths.get(key, [])]
        expected = [(settings.root / c).resolve() for c in categories]
        if actual[:len(expected)] != expected:
            return False
        if any((settings.source / c).resolve() not in actual[len(expected):] for c in categories):
            return False
    return True
