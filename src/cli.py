"""
Unified `autodl` console script.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Sequence

import yaml

from src.core.runtime import (
    CONFIG_KEY_ALIASES,
    DEFAULT_BASE_DIR,
    DEFAULT_COMFY_DIR,
    DEFAULT_CONFIG_FILE,
    DEFAULT_CACHE_DIR,
    DEFAULT_DOWNLOADS_DIR,
    DEFAULT_MODELS_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SECRETS_FILE,
    SECRET_KEY_ALIASES,
    DEFAULT_WORKSPACE_DATA_NAME,
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_TEMP_DIR,
    normalize_config_key,
    normalize_secret_key,
    require_managed_storage_mount,
    resolve_runtime_config,
)
from src.lib.utils import load_yaml, save_yaml


PATH_CONFIG_KEYS = {
    "base_dir", "workspace_dir", "workspace_data_dir", "comfy_dir",
    "models_dir", "output_dir", "downloads_dir", "cache_dir", "temp_dir", "python_env_dir",
}
CONFIG_SET_KEYS = tuple(CONFIG_KEY_ALIASES.keys())
SECRET_SET_KEYS = tuple(SECRET_KEY_ALIASES.keys())


def _code_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _format_yaml(data: dict) -> str:
    if not data:
        return "{}"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()


def _normalize_config_value(key: str, value: str) -> str:
    if key in PATH_CONFIG_KEYS or key in {"local_models_dir", "model_presets_dir"}:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(value)))
    return value


def _save_local_yaml(path: Path, data: dict, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        path.parent.chmod(0o700)
    save_yaml(path, data)
    if mode is not None:
        path.chmod(mode)


def _write_init_config(args: argparse.Namespace) -> None:
    data = load_yaml(args.config_file)
    defaults = {
        "base_dir": DEFAULT_BASE_DIR, "comfy_dir": DEFAULT_COMFY_DIR,
        "models_dir": DEFAULT_MODELS_DIR, "output_dir": DEFAULT_OUTPUT_DIR,
        "downloads_dir": DEFAULT_DOWNLOADS_DIR, "cache_dir": DEFAULT_CACHE_DIR,
        "temp_dir": DEFAULT_TEMP_DIR, "python_env_dir": Path("/root/.venvs/comfyui"),
    }
    for key, default in defaults.items():
        value = getattr(args, key, None) or data.get(key) or default
        data[key] = _normalize_config_value(key, str(value))
    for key, suffix in (("workspace_dir", DEFAULT_WORKSPACE_NAME),
                        ("workspace_data_dir", DEFAULT_WORKSPACE_DATA_NAME)):
        value = getattr(args, key) or data.get(key) or (Path(data["base_dir"]) / suffix)
        data[key] = _normalize_config_value(key, str(value))
    # Use the same process-level path overrides as setup/start/migrate, without
    # persisting transient environment values into the user's configuration.
    effective = dict(data)
    for key in PATH_CONFIG_KEYS - {"python_env_dir"}:
        override = os.environ.get("AUTODL_" + key.upper())
        if key == "models_dir":
            override = override or os.environ.get("COMFYUI_MODELS_DIR")
        if override:
            effective[key] = _normalize_config_value(key, override)
    from src.lib.migration import MigrationManager
    layout = MigrationManager(Path(effective["comfy_dir"]), Path(effective["models_dir"]),
                        Path(effective["output_dir"]), Path(effective["workspace_data_dir"]) / "user", manage_models=False)
    layout.validate()
    paths = [Path(effective[key]) for key in PATH_CONFIG_KEYS]
    require_managed_storage_mount(*paths)
    from src.core.python_env import validate_env_path
    validate_env_path(Path(data["python_env_dir"]))
    for key in ("workspace_dir", "workspace_data_dir", "models_dir", "output_dir",
                "downloads_dir", "cache_dir", "temp_dir"):
        Path(effective[key]).mkdir(parents=True, exist_ok=True)
    layout.initialize()
    if load_yaml(args.config_file) != data:
        _save_local_yaml(args.config_file, data)
    from src.addons.models.preset.environment import Settings, configure
    settings = Settings.load(args.config_file)
    require_managed_storage_mount(settings.source, settings.root)
    settings.root.mkdir(parents=True, exist_ok=True)
    if (settings.comfy / "main.py").is_file():
        configure(settings)
    print(f"配置已就绪: {args.config_file}")


def _dispatch_init(args: argparse.Namespace) -> None:
    """Persist runtime paths, then bring up the configured network backend."""
    _write_init_config(args)

    from src.lib.network import setup_network

    setup_network(config_file=args.config_file)


def _dispatch_config(args: argparse.Namespace) -> None:
    config_file = args.config_file

    if args.config_command == "path":
        print(config_file)
        return

    data = load_yaml(config_file)

    if args.config_command == "show":
        print(_format_yaml(data))
        return

    key = normalize_config_key(args.key)

    if args.config_command == "set":
        data[key] = _normalize_config_value(key, args.value)
        _save_local_yaml(config_file, data)
        print(f"配置已写入: {config_file}")
        print(f"{key}: {data[key]}")
        return

    if args.config_command == "unset":
        existed = key in data
        data.pop(key, None)
        _save_local_yaml(config_file, data)
        print(f"配置已更新: {config_file}")
        print(f"{key}: {'removed' if existed else 'not set'}")
        return

    raise SystemExit(f"未知 config 命令: {args.config_command}")


def _dispatch_secrets(args: argparse.Namespace) -> None:
    secrets_file = args.secrets_file

    if args.secrets_command == "list":
        data = load_yaml(secrets_file)
        for public_key in SECRET_SET_KEYS:
            key = normalize_secret_key(public_key)
            print(f"{public_key}: {'set' if data.get(key) else 'unset'}")
        return

    data = load_yaml(secrets_file)
    key = normalize_secret_key(args.key)

    if args.secrets_command == "set":
        value = args.value
        if value is None:
            value = getpass.getpass(f"{args.key}: ")
        if not value:
            raise SystemExit("secret value is empty")
        data[key] = value
        _save_local_yaml(secrets_file, data, mode=0o600)
        print(f"secret 已写入: {secrets_file}")
        print(f"{args.key}: set")
        return

    if args.secrets_command == "unset":
        existed = key in data
        data.pop(key, None)
        _save_local_yaml(secrets_file, data, mode=0o600)
        print(f"secret 已更新: {secrets_file}")
        print(f"{args.key}: {'removed' if existed else 'not set'}")
        return

    raise SystemExit(f"未知 secrets 命令: {args.secrets_command}")


def _dispatch_lifecycle(action: str, argv: Sequence[str]) -> None:
    from src.main import main as lifecycle_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["autodl", action, *argv]
        lifecycle_main()
    finally:
        sys.argv = original_argv


def _dispatch_status(command: str, argv: Sequence[str]) -> None:
    from src.status import main as status_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["autodl", command, *argv]
        status_main()
    finally:
        sys.argv = original_argv


def _dispatch_model(argv: Sequence[str]) -> None:
    from src.addons.models.downloader import main as model_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["model", *argv]
        model_main()
    finally:
        sys.argv = original_argv


def _dispatch_turbo() -> None:
    from src.lib.network.manager import export_env_shell

    output = export_env_shell()
    if output:
        print(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoDL ComfyUI workspace manager")
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init", help="prepare storage links and proxy on each boot")
    init.add_argument("--base-dir", type=Path, default=None)
    init.add_argument("--workspace-dir", type=Path)
    init.add_argument("--workspace-data-dir", type=Path)
    init.add_argument("--comfy-dir", type=Path, default=None)
    init.add_argument("--models-dir", type=Path)
    init.add_argument("--output-dir", type=Path)
    init.add_argument("--downloads-dir", type=Path)
    init.add_argument("--cache-dir", type=Path)
    init.add_argument("--temp-dir", type=Path)
    init.add_argument("--python-env-dir", type=Path)
    init.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)

    migrate = sub.add_parser("migrate", help="merge conflicting data directories and establish links")
    migrate.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)

    config = sub.add_parser("config", help="manage non-sensitive local config")
    config.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="show current config")
    config_sub.add_parser("path", help="print config path")
    config_set = config_sub.add_parser("set", help="set config value")
    config_set.add_argument("key", choices=CONFIG_SET_KEYS)
    config_set.add_argument("value")
    config_unset = config_sub.add_parser("unset", help="unset config value")
    config_unset.add_argument("key", choices=CONFIG_SET_KEYS)

    secrets = sub.add_parser("secrets", help="manage local secrets")
    secrets.add_argument("--secrets-file", type=Path, default=DEFAULT_SECRETS_FILE)
    secrets_sub = secrets.add_subparsers(dest="secrets_command", required=True)
    secrets_set = secrets_sub.add_parser("set", help="set a secret")
    secrets_set.add_argument("key", choices=SECRET_SET_KEYS)
    secrets_set.add_argument("value", nargs="?")
    secrets_sub.add_parser("list", help="list configured secrets")
    secrets_unset = secrets_sub.add_parser("unset", help="unset a secret")
    secrets_unset.add_argument("key", choices=SECRET_SET_KEYS)

    for action in ("setup", "start", "stop"):
        p = sub.add_parser(action, help=f"run {action} lifecycle")
        p.add_argument("--debug", action="store_true")
        if action == "start":
            p.add_argument("--vram-mode", choices=["high", "normal"],
                           help="显存模式（默认 high；normal 用于对照测试）")

    sub.add_parser("status", help="quick read-only status")
    sub.add_parser("doctor", help="deep read-only diagnostics")
    sub.add_parser("turbo", help="print shell exports for network env")

    model = sub.add_parser("model", aliases=["models"], help="model management (including preset copying)", add_help=False)
    model.add_argument("model_args", nargs=argparse.REMAINDER)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("model", "models"):
        if len(argv) > 1 and argv[1] == "preset":
            from src.addons.models.preset.cli import main as preset_main
            preset_main(argv[2:])
        else:
            _dispatch_model(argv[1:])
        return

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        _dispatch_init(args)
        return

    if args.command == "migrate":
        from src.lib.migration import MigrationManager
        runtime = resolve_runtime_config(_code_root(), config_file=args.config_file)
        MigrationManager(runtime.comfy_dir, runtime.models_dir, runtime.output_dir,
                   runtime.workspace_data_dir / "user", manage_models=False).migrate()
        print("数据迁移与链接处理完成；跳过项请查看警告。")
        return

    if args.command == "config":
        _dispatch_config(args)
        return

    if args.command == "secrets":
        _dispatch_secrets(args)
        return

    if args.command in ("setup", "start", "stop"):
        lifecycle_args = []
        if args.debug:
            lifecycle_args.append("--debug")
        if args.command == "start" and args.vram_mode:
            lifecycle_args.extend(["--vram-mode", args.vram_mode])
        _dispatch_lifecycle(args.command, lifecycle_args)
        return

    if args.command in ("status", "doctor"):
        _dispatch_status(args.command, [])
        return

    if args.command == "turbo":
        _dispatch_turbo()
        return

    if args.command == "model":
        _dispatch_model(args.model_args)
        return

    runtime = resolve_runtime_config(_code_root())
    parser.print_help()
    print(f"\nconfig: {runtime.config_file}")


if __name__ == "__main__":
    main()
