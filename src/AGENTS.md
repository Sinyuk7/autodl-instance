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

1. `system` - UV package manager, cache migration
2. `torch_engine` - PyTorch CUDA setup
3. `comfy_core` - ComfyUI installation
4. `workspace` - Local persistent working data
5. `models` - Model storage migration and layout

## CONVENTIONS

- Plugins are classes in `addons/{name}/plugin.py`
- Must inherit `BaseAddon` from `core.interface`
- Implement only the `setup()`, `start()`, and `stop()` hooks the plugin owns
- Plugin name = directory name (accessed via `self.name`)
- Do not make inspection commands depend on a healthy lifecycle pipeline
- The missing `addons/torch_engine/plugin.py` currently prevents lifecycle imports; preserve this as an explicit known failure until it is repaired and tested
