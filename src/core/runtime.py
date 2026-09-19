"""
Runtime path and config helpers.

This module is the single place that translates install-time code resources,
AutoDL data-disk paths, user configuration, and data-repo metadata into the
paths used by the rest of the app.
"""
import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.lib.utils import load_yaml, save_yaml


PACKAGE_NAME = "autodl-instance"
DEFAULT_TOOL_VERSION = "0.1.0"

DEFAULT_BASE_DIR = Path("/root/autodl-tmp")
DEFAULT_COMFY_DIR = Path("/root/ComfyUI")
DEFAULT_WORKSPACE_NAME = "autodl-workspace"
DEFAULT_WORKSPACE_DATA_NAME = "comfyui-workspace"
DEFAULT_MODELS_NAME = "models"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / PACKAGE_NAME
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_SECRETS_FILE = DEFAULT_CONFIG_DIR / "secrets.yaml"
DATA_REPO_META_DIR = ".autodl-instance"
DATA_REPO_SCHEMA_VERSION_FILE = "data-schema-version"
DATA_REPO_TOOL_VERSION_FILE = "tool-version"
DATA_REPO_SCHEMA_VERSION = "1"

CONFIG_KEY_ALIASES = {
    "base-dir": "base_dir",
    "workspace-dir": "workspace_dir",
    "workspace-data-dir": "workspace_data_dir",
    "comfy-dir": "comfy_dir",
    "models-dir": "models_dir",
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
    config_file: Path
    secrets_file: Path
    local_config: Dict[str, Any]
    local_secrets: Dict[str, Any]


def get_tool_version() -> str:
    """Return installed package version, falling back in source checkouts."""
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return DEFAULT_TOOL_VERSION


def _expand_path(value: Any) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


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
        or (base_dir / DEFAULT_MODELS_NAME)
    )

    return RuntimeConfig(
        code_root=code_root.resolve(),
        base_dir=base_dir,
        workspace_dir=workspace_dir,
        workspace_data_dir=workspace_data_dir,
        comfy_dir=comfy_dir,
        models_dir=models_dir,
        config_file=config_file,
        secrets_file=secrets_file,
        local_config=config,
        local_secrets=secrets,
    )
