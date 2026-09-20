"""Model presets only copy missing files; they never activate or delete models."""
import argparse
import json
from pathlib import Path
import yaml
from src.core.runtime import DEFAULT_CONFIG_FILE
from .copy import ModelCopier, load_preset
from .environment import Settings, check_storage, configure, probe, priority_ready, configuration_ready


def report(value):
    value = dict(value)
    for key, item in list(value.items()):
        if key.endswith("_bytes") and isinstance(item, int):
            value[key[:-6] + "_GiB"] = round(item / 1024 ** 3, 3)
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autodl models preset", description="Copy preset models from fs to tmp; existing files are skipped")
    parser.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show"); show.add_argument("name")
    copy = commands.add_parser("copy", aliases=["use"], help="copy missing files (use is a compatibility alias)")
    copy.add_argument("name"); copy.add_argument("--dry-run", action="store_true")
    commands.add_parser("status")
    commands.add_parser("configure", help="write fixed tmp-first, fs-second search paths")
    args = parser.parse_args(argv)
    try:
        settings = Settings.load(args.config_file)
        copier = ModelCopier(settings.source, settings.root)
        if args.command == "list":
            entries = []
            for path in sorted(settings.presets.glob("*.yaml")):
                try:
                    preset = load_preset(settings.presets, path.stem)
                    entries.append({"name": path.stem, "description": preset["description"], "models": len(preset["models"])})
                except (ValueError, OSError, yaml.YAMLError) as exc:
                    entries.append({"name": path.stem, "error": str(exc)})
            report({"presets_directory": str(settings.presets), "presets": entries})
        elif args.command == "show":
            report(load_preset(settings.presets, args.name))
        elif args.command == "configure":
            check_storage(settings)
            report(configure(settings))
        elif args.command in ("copy", "use"):
            preset = load_preset(settings.presets, args.name)
            check_storage(settings)
            if args.dry_run:
                plan = copier.plan(preset)
                report(plan)
                if plan["result"] != "READY": raise SystemExit(1)
            else:
                report(copier.copy(preset))
        elif args.command == "status":
            live = probe(settings)
            report({"source": str(settings.source), "local": str(settings.root),
                    "configured": configuration_ready(settings),
                    "priority_ready": priority_ready(settings, live["paths"]),
                    "service": live["state"]})
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as exc:
        parser.exit(1, f"Error: {exc}\n")
