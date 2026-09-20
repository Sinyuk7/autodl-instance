# autodl-instance Knowledge Base

**Updated:** 2026-09-19
**Language:** Python 3.10+  
**Purpose:** AutoDL + ComfyUI operations toolkit and on-host knowledge base

## OVERVIEW

Collection of inspectable diagnostics, installers, lifecycle helpers, and recovery tools for ComfyUI on AutoDL. Codex CLI is expected to inspect the real host first and maintain the tools from `/root/autodl-instance`; do not assume the full pipeline is healthy or appropriate for every repair.

## STRUCTURE

```
.
├── src/              # Main source (plugin architecture)
│   ├── addons/       # Lifecycle plugins and task modules
│   ├── core/         # Abstract base classes & ports
│   ├── lib/          # Reusable libraries
│   └── main.py       # Entry point
├── tests/            # unit/ + integration/
├── scripts/          # Shell utilities
├── openspec/         # JSON schemas
├── dcos/             # Docker/config assets
└── init.sh           # Bootstrap entry
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add new lifecycle step | `src/addons/*/plugin.py` | Inherit `BaseAddon`, implement setup/start/stop as needed |
| Modify install flow | `src/main.py:create_pipeline()` | Explicit ordered plugin list; inspect the current entries |
| Shared state between plugins | `src/core/artifacts.py` | `Artifacts` dataclass persists to `.artifacts.json` |
| CLI command dispatch | `src/cli.py`, `src/main.py:execute()` | Handles status/doctor and setup/start/stop actions |
| Network/proxy config | `src/lib/network/` | Mutating setup only; keep inspection and stop paths independent |
| Download strategies | `src/lib/download/` | HuggingFace/CivitAI/aria2 backends |
| Test mocks | `tests/mocks.py` | `MockContext` for unit tests |

## CONVENTIONS

**Plugin Development:**
- Lifecycle addons normally use `src/addons/{name}/plugin.py`; task-only or incomplete modules may not
- Plugins declare dependencies via `artifacts` DTO, not direct imports
- Lifecycle hooks are `setup()`, `start()`, and `stop()`; inspect the current pipeline before changing order.
- State persistence via `ctx.state.mark_completed()` / `is_completed()`

**Configuration:**
- Public params → `manifest.yaml` (scanned at startup)
- Secrets → `secrets.yaml` (gitignored, manual load)
- Cross-instance state → `.artifacts.json` (auto-generated)

**Error Handling:**
- Use `ctx.cmd.run()` not raw `subprocess` (friendly error messages)
- Log to file + terminal via `src.core.utils.logger`

## ANTI-PATTERNS

| DON'T | DO INSTEAD | WHY |
|-------|------------|-----|
| Use `Dict` for context | Use `AppContext` dataclass | Type safety, IDE completion |
| Raw `subprocess.run()` | `ctx.cmd.run()` | Consistent error handling |
| Direct file access for config | `self.get_manifest(ctx)` | Centralized config loading |
| Hardcode paths | Use `ctx.base_dir`, `ctx.comfy_dir` | Portable across environments |
| Skip state checks | Check `ctx.state.is_completed()` | Ensures idempotency |

## COMMANDS

```bash
# Initial setup (run once)
autodl init
autodl setup [--debug]
# Or directly:
autodl setup [--debug]

# Start ComfyUI
autodl start [--debug]

# Stop ComfyUI and owned helper processes
autodl stop [--debug]

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## DEPENDENCIES

Core: `pluggy>=1.3.0`, `PyYAML>=6.0.1`, `rich>=13.0.0`, `prompt_toolkit>=3.0.0`

## NOTES

- AutoDL source checkout belongs on the system disk at `/root/autodl-instance`.
- `/root` is normally a 30GB system disk. Keep source, ComfyUI, Python environments, Codex, proxy software, and host configuration here so the environment can be saved as a private AutoDL image; keep models and large caches out.
- Data盘 is `/root/autodl-tmp`, normally 50GB. Verify it is a real mount before writes. Use it for high-I/O working data, temporary output, caches, and selected active models; it is not included in system images and has no redundancy guarantee.
- `/root/autodl-fs` is shared file storage with redundant copies and survives instance release. Use it as durable storage for important data, code backups, workflows, and the full model library. Its I/O is slower, so stage active data to the local data disk when useful.
- Treat saved images as the user's private environment. Credentials may remain on the system disk with restrictive permissions; never share such an image without removing them first.
- AutoDL cannot import an external custom image. Saving the full system disk as an AutoDL image is a control-plane action performed after shutdown; loading/replacing an image clears the system disk but leaves the local data disk unchanged.
- AutoDL images can technically be shared, but sharing is not the default workflow. If explicitly requested, first remove subscription URLs, tokens, SSH private keys, Codex login data, and other machine secrets.
- Saving an image captures only the system disk. Same-region instance cloning uses the system disk as its template and can optionally copy the local data disk. Shared file storage is mounted separately and is not part of either image.
- Do not move plaintext secrets to the local data disk or shared file storage merely to keep them outside the image.
- Ports 6006/6008 mapped to public by AutoDL
- `uv` used for fast Python package management
- `comfy-cli` manages ComfyUI installation
- Read-only inspection must not initialize networking or mutate host state.
- Prefer direct Mihomo process management and per-command proxy variables; do not require global shell proxy injection.
- Never print or commit proxy profiles, subscription URLs, tokens, private keys, or local secrets.
- comfy-cli manages Torch and ComfyUI dependencies in `/root/.venvs/comfyui`; never fall back to base Conda or pin Torch independently.
- CLI uses editable installation from `/root/autodl-instance`. No partial lifecycle flags or generated shell aliases.
- `init` prepares missing directories, fixed tmp/fs model paths, safe output/user links and networking each boot; `migrate` only merges output/user data; `setup` only installs programs/dependencies. Model help/list/status/types must remain read-only.
- Output defaults to `/root/autodl-fs/output`; downloads/cache/temp use `/root/autodl-tmp/ComfyUI`.
- Proxy profiles belong in `~/.config/autodl-instance/mihomo` on the system disk.

- Shared migration module: `src/lib/migration`. init handles unambiguous output/user moves/links; migrate allows explicit conflict merging there. Model files are never moved by init/migrate.


## Model directory policy (current)

- Models use `/root/autodl-tmp/ComfyUI/models` first and `/root/autodl-fs/models` second via fixed ComfyUI extra_model_paths.yaml blocks.
- `init/migrate` must not migrate model files or create fs category links; their output/user migration behavior remains.
- Presets only copy missing fs files into tmp at the same relative path. Existing files are skipped, never overwritten or automatically deleted. There is no active preset, cache ownership, eviction, or reset.
- Downloads write beside their final model as `.part` and publish on success. Do not introduce a second hidden model root or route new model downloads into a separate staging tree.
