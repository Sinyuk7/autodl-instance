"""
Runtime path and config helpers.

This module is the single place that translates install-time code resources,
AutoDL storage paths, and local user configuration into the paths used by the
rest of the app.
"""
import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.lib.utils import load_yaml


PACKAGE_NAME = "autodl-instance"
DEFAULT_TOOL_VERSION = "0.1.0"

DEFAULT_BASE_DIR = Path("/root/autodl-tmp")
DEFAULT_COMFY_DIR = Path("/root/ComfyUI")
DEFAULT_WORKSPACE_NAME = "autodl-workspace"
DEFAULT_WORKSPACE_DATA_NAME = "comfyui-workspace"
DEFAULT_LOCAL_COMFY_DIR = DEFAULT_BASE_DIR / "ComfyUI"
DEFAULT_SHARED_COMFY_DIR = Path("/root/autodl-fs")
DEFAULT_MODELS_DIR = DEFAULT_SHARED_COMFY_DIR / "models"
DEFAULT_OUTPUT_DIR = DEFAULT_SHARED_COMFY_DIR / "output"
DEFAULT_DOWNLOADS_DIR = DEFAULT_LOCAL_COMFY_DIR / "downloads"
DEFAULT_CACHE_DIR = DEFAULT_LOCAL_COMFY_DIR / "cache"
DEFAULT_TEMP_DIR = DEFAULT_LOCAL_COMFY_DIR / "temp"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / PACKAGE_NAME
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_SECRETS_FILE = DEFAULT_CONFIG_DIR / "secrets.yaml"
MANAGED_STORAGE_ROOTS = (Path("/root/autodl-tmp"), Path("/root/autodl-fs"))
CONFIG_KEY_ALIASES = {
    "base-dir": "base_dir",
    "workspace-dir": "workspace_dir",
    "workspace-data-dir": "workspace_data_dir",
    "comfy-dir": "comfy_dir",
    "models-dir": "models_dir",
    "output-dir": "output_dir",
    "downloads-dir": "downloads_dir",
    "cache-dir": "cache_dir",
    "temp-dir": "temp_dir",
    "python-env-dir": "python_env_dir",
}

SECRET_KEY_ALIASES = {
    "hf-token": "hf_token",
    "civitai-token": "civitai_token",
    "mihomo-subscription-url": "mihomo_subscription_url",
}


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved runtime paths and local configuration."""

    code_root: Path
    base_dir: Path
    workspace_dir: Path
    workspace_data_dir: Path
    comfy_dir: Path
    models_dir: Path
    output_dir: Path
    downloads_dir: Path
    cache_dir: Path
    temp_dir: Path
    config_file: Path
    secrets_file: Path
    local_config: Dict[str, Any]
    local_secrets: Dict[str, Any]
    python_env_dir: Path = Path('/root/.venvs/comfyui')


def require_managed_storage_mount(*paths: Path) -> None:
    """Refuse writes below known AutoDL storage roots when their mount is absent."""
    for path in paths:
        resolved_path = path.expanduser().resolve()
        for configured_root in MANAGED_STORAGE_ROOTS:
            root = configured_root.resolve()
            if resolved_path != root and root not in resolved_path.parents:
                continue
            if not root.is_mount():
                raise RuntimeError(
                    f"AutoDL storage is not mounted: {configured_root}; "
                    f"refusing to write {resolved_path}"
                )
            break


def configure_cache_environment(config: RuntimeConfig) -> None:
    """Route rebuildable package and model-download caches to the local data disk."""
    cache_dir = config.cache_dir
    values = {
        "XDG_CACHE_HOME": cache_dir,
        "UV_CACHE_DIR": cache_dir / "uv",
        "PIP_CACHE_DIR": cache_dir / "pip",
        "HF_HOME": cache_dir / "huggingface",
        "HF_HUB_CACHE": cache_dir / "huggingface" / "hub",
        "HF_XET_CACHE": cache_dir / "huggingface" / "xet",
        "TORCH_HOME": cache_dir / "torch",
        "AUTODL_DOWNLOADS_DIR": config.downloads_dir,
    }
    for key, value in values.items():
        os.environ[key] = str(value)


def get_tool_version() -> str:
    """Return installed package version, falling back in source checkouts."""
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return DEFAULT_TOOL_VERSION


def _expand_path(value: Any) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(value)))))


def normalize_config_key(key: str) -> str:
    """Normalize public CLI config keys to the persisted YAML key."""
    return CONFIG_KEY_ALIASES.get(key, key.replace("-", "_"))


def normalize_secret_key(key: str) -> str:
    """Normalize public CLI secret keys to the persisted YAML key."""
    return SECRET_KEY_ALIASES.get(key, key.replace("-", "_"))


def load_local_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    """Load non-sensitive user config from ~/.config/autodl-instance/config.yaml."""
    return load_yaml(config_file)


def load_local_secrets(secrets_file: Path = DEFAULT_SECRETS_FILE) -> Dict[str, Any]:
    """Load local sensitive config from ~/.config/autodl-instance/secrets.yaml."""
    return load_yaml(secrets_file)


def resolve_runtime_config(
    code_root: Path,
    config_file: Path = DEFAULT_CONFIG_FILE,
    secrets_file: Path = DEFAULT_SECRETS_FILE,
) -> RuntimeConfig:
    """Resolve runtime paths from defaults, local config, then env overrides."""
    config = load_local_config(config_file)
    secrets = load_local_secrets(secrets_file)

    base_dir = (
        _expand_path(os.environ.get("AUTODL_BASE_DIR"))
        or _expand_path(config.get("base_dir"))
        or DEFAULT_BASE_DIR
    )
    workspace_dir = (
        _expand_path(os.environ.get("AUTODL_WORKSPACE_DIR"))
        or _expand_path(config.get("workspace_dir"))
        or (base_dir / DEFAULT_WORKSPACE_NAME)
    )
    workspace_data_dir = (
        _expand_path(os.environ.get("AUTODL_WORKSPACE_DATA_DIR"))
        or _expand_path(config.get("workspace_data_dir"))
        or (base_dir / DEFAULT_WORKSPACE_DATA_NAME)
    )
    comfy_dir = (
        _expand_path(os.environ.get("AUTODL_COMFY_DIR"))
        or _expand_path(config.get("comfy_dir"))
        or DEFAULT_COMFY_DIR
    )
    models_dir = (
        _expand_path(os.environ.get("AUTODL_MODELS_DIR"))
        or _expand_path(os.environ.get("COMFYUI_MODELS_DIR"))
        or _expand_path(config.get("models_dir"))
        or DEFAULT_MODELS_DIR
    )
    output_dir = (
        _expand_path(os.environ.get("AUTODL_OUTPUT_DIR"))
        or _expand_path(config.get("output_dir"))
        or DEFAULT_OUTPUT_DIR
    )
    downloads_dir = (
        _expand_path(os.environ.get("AUTODL_DOWNLOADS_DIR"))
        or _expand_path(config.get("downloads_dir"))
        or DEFAULT_DOWNLOADS_DIR
    )
    cache_dir = (
        _expand_path(os.environ.get("AUTODL_CACHE_DIR"))
        or _expand_path(config.get("cache_dir"))
        or DEFAULT_CACHE_DIR
    )
    temp_dir = (
        _expand_path(os.environ.get("AUTODL_TEMP_DIR"))
        or _expand_path(config.get("temp_dir"))
        or DEFAULT_TEMP_DIR
    )

    return RuntimeConfig(
        code_root=code_root.resolve(),
        base_dir=base_dir,
        workspace_dir=workspace_dir,
        workspace_data_dir=workspace_data_dir,
        comfy_dir=comfy_dir,
        models_dir=models_dir,
        output_dir=output_dir,
        downloads_dir=downloads_dir,
        cache_dir=cache_dir,
        temp_dir=temp_dir,
        config_file=config_file,
        secrets_file=secrets_file,
        local_config=config,
        local_secrets=secrets,
        python_env_dir=_expand_path(config.get('python_env_dir')) or Path('/root/.venvs/comfyui'),
    )
