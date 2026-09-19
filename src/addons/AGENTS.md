# src/addons/ Knowledge Base

**Purpose:** Lifecycle plugins - each manages one domain of the setup process

## STRUCTURE

```
addons/
├── system/          # System tools and package tooling
├── comfy_core/      # ComfyUI core lifecycle
├── workspace/       # Persistent user/output directory links
└── models/          # Model layout and management
```

## PLUGIN TEMPLATE

```python
# src/addons/my_feature/plugin.py
from src.core.interface import BaseAddon, AppContext

class MyAddon(BaseAddon):
    def setup(self, ctx: AppContext) -> None:
        # Check if already done
        if ctx.state.is_completed("MY_FEATURE"):
            return
        # ... do work ...
        ctx.state.mark_completed("MY_FEATURE")
    
    def start(self, ctx: AppContext) -> None:
        pass  # Or implement if needed
    
    def stop(self, ctx: AppContext) -> None:
        pass  # Or implement owned-process cleanup/persistence
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Install system tools | `system/plugin.py` - uv and dedicated venv |
| PyTorch setup | `comfy_core/plugin.py`; comfy-cli manages dependencies in the dedicated venv |
| ComfyUI install | `comfy_core/plugin.py` - Uses `comfy-cli` |
| Persistent workspace links | `workspace/plugin.py` - Connect system-disk ComfyUI to data-disk state |
| Model downloads | `models/downloader.py` - staging via aria2 |

## CONVENTIONS

**Each addon directory contains:**
- `plugin.py` - Implementation (required)
- `manifest.yaml` - Public configuration (required)
- `schema.py` - Pydantic models for manifest (optional)
- `tasks/` - Sub-tasks for complex addons (optional)
- `secrets.yaml` - Private credentials (gitignored, optional)
- `secrets.yaml.example` - Template for secrets (required if secrets.yaml exists)

**State Management:**
- Always check `ctx.state.is_completed(StateKey.X)` before work
- Mark completion with `ctx.state.mark_completed(StateKey.X)`
- State persists in `workspace_dir/.autodl_state/`; Comfy readiness is also bound to its venv

**Artifacts (cross-plugin data):**
- Write: `ctx.artifacts.my_field = value`
- Read: `value = ctx.artifacts.my_field`
- Persisted automatically after setup completes

**Host safety:**
- Verify `/root/autodl-tmp` is a real data-disk mount before large writes
- Manage only processes whose ownership is established; never kill an arbitrary port occupant
- Keep ComfyUI Python dependencies in a dedicated environment, not AutoDL's base Conda/Jupyter environment
