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
    DEFAULT_MODELS_NAME,
    DEFAULT_SECRETS_FILE,
    SECRET_KEY_ALIASES,
    DEFAULT_USERDATA_NAME,
    DEFAULT_WORKSPACE_NAME,
    find_legacy_userdata_dirs,
    normalize_config_key,
    normalize_secret_key,
    resolve_runtime_config,
)
from src.lib.utils import load_yaml, save_yaml


PATH_CONFIG_KEYS = {"base_dir", "workspace_dir", "userdata_dir", "comfy_dir", "models_dir"}
CONFIG_SET_KEYS = tuple(CONFIG_KEY_ALIASES.keys())
SECRET_SET_KEYS = tuple(SECRET_KEY_ALIASES.keys())


def _code_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _format_yaml(data: dict) -> str:
    if not data:
        return "{}"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()


def _normalize_config_value(key: str, value: str) -> str:
    if key in PATH_CONFIG_KEYS:
        return str(Path(os.path.expandvars(os.path.expanduser(value))).resolve())
    return value


def _save_local_yaml(path: Path, data: dict, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        path.parent.chmod(0o700)
    save_yaml(path, data)
    if mode is not None:
        path.chmod(mode)


def _write_init_config(args: argparse.Namespace) -> None:
    base_dir = args.base_dir
    workspace_dir = args.workspace_dir or (base_dir / DEFAULT_WORKSPACE_NAME)
    userdata_dir = args.userdata_dir or (base_dir / DEFAULT_USERDATA_NAME)
    models_dir = args.models_dir or (base_dir / DEFAULT_MODELS_NAME)

    data = {
        "base_dir": str(base_dir),
        "workspace_dir": str(workspace_dir),
        "userdata_dir": str(userdata_dir),
        "comfy_dir": str(args.comfy_dir),
        "models_dir": str(models_dir),
    }
    if args.userdata_repo:
        data["userdata_repo"] = args.userdata_repo

    config_file = args.config_file
    _save_local_yaml(config_file, data)

    workspace_dir.mkdir(parents=True, exist_ok=True)
    userdata_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"配置已写入: {config_file}")
    print(f"workspace_dir: {workspace_dir}")
    print(f"userdata_dir: {userdata_dir}")


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


def _dispatch_migrate(args: argparse.Namespace) -> None:
    runtime = resolve_runtime_config(_code_root(), config_file=args.config_file)

    if args.migrate_command == "detect-old-layout":
        legacy_dirs = find_legacy_userdata_dirs(runtime.code_root, runtime.base_dir, runtime.userdata_dir)
        if legacy_dirs:
            print("检测到旧布局数据目录")
            for path in legacy_dirs:
                print(f"old: {path}")
            print(f"new: {runtime.userdata_dir}")
            print("此命令只读检测，不会移动或删除任何文件。")
        else:
            print("未检测到旧布局数据目录。")
        return

    raise SystemExit(f"未知 migrate 命令: {args.migrate_command}")


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

    init = sub.add_parser("init", help="bind local config and userdata repo")
    init.add_argument("--userdata-repo", default="", help="Git URL for the user data repo")
    init.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    init.add_argument("--workspace-dir", type=Path)
    init.add_argument("--userdata-dir", type=Path)
    init.add_argument("--comfy-dir", type=Path, default=DEFAULT_COMFY_DIR)
    init.add_argument("--models-dir", type=Path)
    init.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)

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

    migrate = sub.add_parser("migrate", help="read-only migration helpers")
    migrate.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)
    migrate_sub = migrate.add_subparsers(dest="migrate_command", required=True)
    migrate_sub.add_parser("detect-old-layout", help="detect old source-layout userdata")

    for action in ("setup", "start", "sync"):
        p = sub.add_parser(action, help=f"run {action} lifecycle")
        p.add_argument("--debug", action="store_true")
        p.add_argument("--until", type=str)
        p.add_argument("--only", type=str)

    sub.add_parser("bye", help="sync then stop proxy")
    sub.add_parser("status", help="quick read-only status")
    sub.add_parser("doctor", help="deep read-only diagnostics")
    sub.add_parser("turbo", help="print shell exports for network env")

    model = sub.add_parser("model", help="model management", add_help=False)
    model.add_argument("model_args", nargs=argparse.REMAINDER)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "model":
        _dispatch_model(argv[1:])
        return

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        print("warning: `autodl init` is deprecated; use `autodl config set ...` instead.", file=sys.stderr)
        _write_init_config(args)
        return

    if args.command == "config":
        _dispatch_config(args)
        return

    if args.command == "secrets":
        _dispatch_secrets(args)
        return

    if args.command == "migrate":
        _dispatch_migrate(args)
        return

    if args.command in ("setup", "start", "sync"):
        lifecycle_args = []
        if args.debug:
            lifecycle_args.append("--debug")
        if args.until:
            lifecycle_args.extend(["--until", args.until])
        if args.only:
            lifecycle_args.extend(["--only", args.only])
        _dispatch_lifecycle(args.command, lifecycle_args)
        return

    if args.command == "bye":
        from src.shutdown import main as shutdown_main

        shutdown_main()
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
