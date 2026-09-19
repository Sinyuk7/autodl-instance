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
./init.sh [--debug]
# Or directly:
python -m src.main setup [--debug] [--until PLUGIN] [--only PLUGIN]

# Start ComfyUI
python -m src.main start [--debug]

# Stop ComfyUI and owned helper processes
python -m src.main stop [--debug]

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## DEPENDENCIES

Core: `pluggy>=1.3.0`, `PyYAML>=6.0.1`, `rich>=13.0.0`, `prompt_toolkit>=3.0.0`

## NOTES

- AutoDL source checkout belongs on the system disk at `/root/autodl-instance`.
- `/root` survives normal shutdown but is cleared by system reset/image replacement; it is rebuildable, not a backup.
- Data盘 is `/root/autodl-tmp`; verify it is a real mount before large writes. It survives system reset but is deleted with instance release and has no redundancy guarantee.
- `/root/autodl-fs` is slower shared file storage suited to compressed backups, not active model or ComfyUI workloads.
- Ports 6006/6008 mapped to public by AutoDL
- `uv` used for fast Python package management
- `comfy-cli` manages ComfyUI installation
- Read-only inspection must not initialize networking or mutate host state.
- Prefer direct Mihomo process management and per-command proxy variables; do not require global shell proxy injection.
- Never print or commit proxy profiles, subscription URLs, tokens, private keys, or local secrets.
- Known baseline defect: `src/addons/torch_engine/plugin.py` is missing while `src/main.py` imports it.
