# src/core/ Knowledge Base

**Purpose:** Core abstractions - interfaces, DTOs, and base implementations

## STRUCTURE

```
core/
├── interface.py    # BaseAddon, AppContext, hookimpl
├── artifacts.py    # Artifacts DTO (cross-plugin data)
├── schema.py       # StateKey, EnvKey enums
├── ports.py        # Abstract interfaces (ICommandRunner, IStateManager)
├── adapters.py     # Concrete implementations
├── task.py         # Task execution utilities
└── utils.py        # Common utilities (logger, helpers)
```

## KEY COMPONENTS

**interface.py:**
- `BaseAddon` - Abstract base for all plugins
- `AppContext` - Dependency injection container
- `hookimpl` - Pluggy hook marker

**artifacts.py:**
- `Artifacts` dataclass - Strongly typed shared state
- Persists to `.artifacts.json` after setup
- Loaded on start/stop to access setup-time data

**ports.py (Interfaces):**
- `ICommandRunner` - Command execution abstraction
- `IStateManager` - State persistence abstraction

**adapters.py (Implementations):**
- `SubprocessRunner` - subprocess-based command runner
- `FileStateManager` - completion-marker file state manager

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add new artifact field | `artifacts.py` - Add dataclass field |
| Add state key | `schema.py` - Add to `StateKey` enum |
| Modify command execution | `adapters.py:SubprocessRunner` |
| Change logging format | `utils.py:setup_logger()` |
| Add base addon capability | `interface.py:BaseAddon` |

## CONVENTIONS

**Port-Adapter Pattern:**
- Define interface in `ports.py`
- Implement in `adapters.py`
- Inject via `AppContext` to addons

**Type Safety:**
- All context data strongly typed (no `Dict[str, Any]`)
- Use `Optional[Path]`, not bare `Path`
- Artifacts uses dataclasses, not dicts

**Extending Artifacts:**
```python
# In artifacts.py
@dataclass
class Artifacts:
    existing_field: Optional[Path] = None
    my_new_field: Optional[str] = None  # Add here
```

Runtime defaults place models/output on shared storage, downloads/cache/temp on local storage and the dedicated Python venv on the system disk. Never resolve ComfyUI Python from ambient Conda.
