"""Copy preset models from shared storage into the local model directory."""
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile

import yaml

CATEGORIES = {"checkpoints", "diffusion_models", "text_encoders", "vae", "clip_vision",
              "controlnet", "loras", "upscale_models", "embeddings", "unet", "clip",
              "instantid", "insightface", "audio_encoders", "configs", "detection",
              "diffusers", "gligen", "hypernetworks", "latent_upscale_models",
              "model_patches", "photomaker", "style_models", "vae_approx",
              "BiRefNet", "background_removal", "frame_interpolation",
              "geometry_estimation", "optical_flow"}
ALIASES = {"unet": "diffusion_models", "clip": "text_encoders"}


def relative_path(value):
    if not isinstance(value, str) or "\\" in value:
        raise ValueError(f"Invalid model path: {value!r}")
    parts = value.split("/")
    if len(parts) < 2 or any(not p or p in (".", "..") or p.startswith(".") for p in parts):
        raise ValueError(f"Unsafe model path: {value!r}")
    if PurePosixPath(value).is_absolute() or parts[0] not in CATEGORIES:
        raise ValueError(f"Unsupported model category/path: {value!r}")
    return value


def safe_path(root, relative):
    """Never follow symlinks in the local directory (including ancestor directories)."""
    path = Path(root) / relative
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Symlink is not allowed in local model path: {part}")
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError(f"Path escapes model directory: {relative}")
    return path


def fingerprint(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Not a regular file: {path}")
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns, "ino": info.st_ino, "dev": info.st_dev}


def load_preset(directory, name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("Invalid preset name")
    path = safe_path(directory, name + ".yaml")
    fingerprint(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("Preset schema version must be 1")
    if data.get("name") != name:
        raise ValueError("Preset name must match its filename")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Preset models must be a non-empty list")
    models = [relative_path(p) for p in models]
    keys = [(ALIASES.get(p.split('/')[0], p.split('/')[0]), p.split('/', 1)[1]) for p in models]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate model name (including category aliases)")
    return {"version": 1, "name": name, "description": data.get("description", ""), "models": models}


class ModelCopier:
    def __init__(self, source, local, progress=print):
        self.source, self.local = Path(source), Path(local)
        self.progress = progress
        if (self.source.resolve().is_relative_to(self.local.resolve())
                or self.local.resolve().is_relative_to(self.source.resolve())):
            raise ValueError("Shared and local model directories must not overlap")

    def paths(self, rel):
        relative_path(rel)
        src = self.source / rel
        if not src.resolve().is_relative_to(self.source.resolve()):
            raise ValueError(f"Source escapes model directory: {rel}")
        return src, safe_path(self.local, rel)

    def plan(self, preset):
        copy, skip, missing = [], [], []
        needed = 0
        for rel in preset["models"]:
            src, dst = self.paths(rel)
            if dst.exists():
                fingerprint(dst)
                if Path(str(dst) + ".aria2").exists():
                    raise ValueError(f"Incomplete legacy download; finish or remove manually: {dst}")
                skip.append(rel)
            elif not src.exists():
                missing.append(rel)
            else:
                needed += fingerprint(src)["size"]
                copy.append(rel)
        ancestor = self.local
        while not ancestor.exists():
            ancestor = ancestor.parent
        free = shutil.disk_usage(ancestor).free
        return {"preset": preset["name"], "copy": copy, "skip": skip, "missing": missing,
                "need_copy_bytes": needed, "free_bytes": free,
                "result": "MISSING_MODELS" if missing else "INSUFFICIENT_SPACE" if needed > free else "READY"}

    def copy(self, preset):
        plan = self.plan(preset)
        if plan["result"] != "READY":
            raise RuntimeError(f"Cannot copy preset: {plan['result']}; missing: {plan['missing']}")
        copied, skipped = [], list(plan["skip"])
        for rel in plan["copy"]:
            src, dst = self.paths(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            before = fingerprint(src)
            self.progress(f"Copying: {rel}")
            # Unique partial files permit concurrent copies without overwriting
            # either the final file or another operation's unfinished data.
            with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=dst.name + ".", suffix=".part", delete=False) as stream:
                partial = Path(stream.name)
                try:
                    with src.open("rb") as source:
                        shutil.copyfileobj(source, stream, 8 * 1024 * 1024)
                    stream.flush()
                    os.fsync(stream.fileno())
                    if fingerprint(src) != before or stream.tell() != before["size"]:
                        raise RuntimeError(f"Source changed during copy: {rel}")
                    # link publishes atomically and fails if a competing writer
                    # has already created the destination. Never replace it.
                    try:
                        os.link(partial, dst)
                    except FileExistsError:
                        skipped.append(rel)
                    else:
                        copied.append(rel)
                finally:
                    partial.unlink(missing_ok=True)
        return {"preset": preset["name"], "copied": copied, "skipped": skipped}
