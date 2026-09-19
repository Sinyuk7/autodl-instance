# src/ Knowledge Base

**Purpose:** Main source directory - plugin architecture implementation

## STRUCTURE

```
src/
├── cli.py           # Unified autodl command dispatch
├── main.py          # Lifecycle pipeline orchestration
├── status.py        # Read-only status and doctor checks
├── addons/          # Lifecycle plugins
├── core/            # Abstract base classes, ports, adapters
└── lib/             # Reusable libraries (download, network)
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add plugin to pipeline | `main.py:create_pipeline()` - append to list |
| Change plugin order | `main.py:create_pipeline()` - reorder list |
| Access manifest config | `main.py:load_manifests()` or `addon.get_manifest(ctx)` |
| CLI argument parsing | `cli.py:build_parser()` and the delegated entry point |
| Add read-only diagnostics | `status.py` - must not initialize networking |
| Context creation | `main.py:create_context()` |

## PLUGIN PIPELINE

Hardcoded execution order (setup):

1. `system` - tools and dedicated ComfyUI venv
2. `comfy_core` - ComfyUI and Torch dependencies via comfy-cli
Data directories and links belong to boot-time `init`; explicit `migrate` moves existing data and preserves conflicts. Neither is part of setup.

## CONVENTIONS

- Plugins are classes in `addons/{name}/plugin.py`
- Must inherit `BaseAddon` from `core.interface`
- Implement only the `setup()`, `start()`, and `stop()` hooks the plugin owns
- Plugin name = directory name (accessed via `self.name`)
- Do not make inspection commands depend on a healthy lifecycle pipeline
- comfy-cli owns Torch installation; installs must target the dedicated ComfyUI venv.
- init prepares directories/links and proxy on each boot; migrate explicitly merges conflicting subdirectories and links them; setup installs only programs and dependencies. Help and model inspection do not initialize networking.
- No --until/--only lifecycle options.

- Shared migration module: `src/lib/migration`. init handles unambiguous child-directory moves/links; migrate allows explicit conflict merging. models/output roots remain physical directories and their regular files are never migrated.
