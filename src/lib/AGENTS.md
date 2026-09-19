# src/lib/ Knowledge Base

**Purpose:** Reusable libraries - download strategies, network management, UI

## STRUCTURE

```
lib/
├── download/       # Multi-strategy downloaders
├── network/        # Network decision, mirrors, proxy backends and state
│   └── proxy/      # Mihomo install/config/process management
├── ui.py           # Terminal UI utilities
└── utils.py        # General utilities
```

## DOWNLOAD STRATEGIES

**HuggingFace (`download/hf_hub.py`):**
- Uses `huggingface_hub` + `hf_xet`
- Version-aware caching
- Token auth via `secrets.yaml`

**CivitAI (`download/aria2.py`):**
- Uses `aria2c` 32-thread
- API token support
- Automatic model info parsing

**Direct URL (`download/aria2.py`):**
- 32 threads, resume support
- Progress tracking via aria2 RPC

## NETWORK MANAGEMENT

**`network/` and `network/proxy/`:**
- Mihomo (Clash) proxy setup
- AutoDL academic acceleration
- GitHub/HuggingFace mirror config
- API token injection

**Mutation boundary:** `setup_network()` may install/start a proxy and modify the current process environment. Do not call it from `status`, `doctor`, `stop`, imports, or other read-only paths.

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add download source | `download/` - New strategy class |
| Modify proxy behavior | `network/manager.py` and `network/proxy/` |
| Add UI prompt | `ui.py` - Rich/prompt_toolkit helpers |
| Utility functions | `utils.py` |

## CONVENTIONS

**Downloaders:**
- Implement common interface (implicit contract)
- Accept `progress_callback` for UI updates
- Return `Path` to downloaded file
- Handle auth via `secrets.yaml` (not params)

**Network:**
- Treat `direct`, `turbo`, `mihomo`, and `unavailable` as distinct observable outcomes
- Start Mihomo independently from exporting proxy variables into a shell
- Prefer per-command proxy variables; local checks must bypass proxies explicitly
- Cache decisions only after validating the selected backend
- Never log subscription URLs, nodes, tokens, or raw private configuration
