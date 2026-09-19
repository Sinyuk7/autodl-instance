from pathlib import Path

from src.core.runtime import (
    DEFAULT_CACHE_DIR,
    DEFAULT_DOWNLOADS_DIR,
    DEFAULT_MODELS_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEMP_DIR,
    configure_cache_environment,
    resolve_runtime_config,
)
from src.lib.utils import save_yaml


def test_resolve_runtime_config_uses_global_config(tmp_path: Path):
    code_root = tmp_path / "code"
    code_root.mkdir()
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {
        "base_dir": str(tmp_path / "data"),
        "workspace_dir": str(tmp_path / "workspace"),
        "workspace_data_dir": str(tmp_path / "workspace-data"),
        "comfy_dir": str(tmp_path / "ComfyUI"),
        "models_dir": str(tmp_path / "models"),
        "output_dir": str(tmp_path / "output"),
        "downloads_dir": str(tmp_path / "downloads"),
        "cache_dir": str(tmp_path / "cache"),
        "temp_dir": str(tmp_path / "temp"),
    })

    runtime = resolve_runtime_config(code_root, config_file=config_file)

    assert runtime.code_root == code_root.resolve()
    assert runtime.base_dir == (tmp_path / "data").resolve()
    assert runtime.workspace_dir == (tmp_path / "workspace").resolve()
    assert runtime.workspace_data_dir == (tmp_path / "workspace-data").resolve()
    assert runtime.comfy_dir == (tmp_path / "ComfyUI").resolve()
    assert runtime.models_dir == (tmp_path / "models").resolve()
    assert runtime.output_dir == (tmp_path / "output").resolve()
    assert runtime.downloads_dir == (tmp_path / "downloads").resolve()
    assert runtime.cache_dir == (tmp_path / "cache").resolve()
    assert runtime.temp_dir == (tmp_path / "temp").resolve()


def test_resolve_runtime_config_env_overrides_config(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {"base_dir": str(tmp_path / "from-config")})
    monkeypatch.setenv("AUTODL_BASE_DIR", str(tmp_path / "from-env"))

    runtime = resolve_runtime_config(tmp_path / "code", config_file=config_file)

    assert runtime.base_dir == (tmp_path / "from-env").resolve()
    assert runtime.workspace_dir == runtime.base_dir / "autodl-workspace"
    assert runtime.workspace_data_dir == runtime.base_dir / "comfyui-workspace"
    assert runtime.models_dir == DEFAULT_MODELS_DIR
    assert runtime.output_dir == DEFAULT_OUTPUT_DIR
    assert runtime.downloads_dir == DEFAULT_DOWNLOADS_DIR
    assert runtime.cache_dir == DEFAULT_CACHE_DIR
    assert runtime.temp_dir == DEFAULT_TEMP_DIR


def test_configure_cache_environment_uses_local_cache(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    cache_dir = tmp_path / "cache"
    downloads_dir = tmp_path / "downloads"
    save_yaml(config_file, {
        "cache_dir": str(cache_dir),
        "downloads_dir": str(downloads_dir),
    })
    runtime = resolve_runtime_config(tmp_path / "code", config_file=config_file)

    configure_cache_environment(runtime)

    assert runtime.cache_dir == cache_dir.resolve()
    assert runtime.downloads_dir == downloads_dir.resolve()
    assert __import__("os").environ["UV_CACHE_DIR"] == str(cache_dir.resolve() / "uv")
    assert __import__("os").environ["HF_HUB_CACHE"] == str(cache_dir.resolve() / "huggingface" / "hub")
    assert __import__("os").environ["AUTODL_DOWNLOADS_DIR"] == str(downloads_dir.resolve())


def test_resolve_runtime_config_loads_local_secrets(tmp_path: Path):
    secrets_file = tmp_path / "secrets.yaml"
    save_yaml(secrets_file, {"hf_token": "secret"})

    runtime = resolve_runtime_config(tmp_path / "code", secrets_file=secrets_file)

    assert runtime.secrets_file == secrets_file
    assert runtime.local_secrets["hf_token"] == "secret"
