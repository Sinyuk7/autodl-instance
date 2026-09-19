# AutoDL Instance 项目架构分析（历史快照）

> 本文包含早期 `sync`、Git 和 userdata 插件设计，与当前源码不完全一致，仅用于理解历史方向，不应作为运行或修改依据。当前入口、插件列表和约束请以源码、根目录 `README.md` 及各级 `AGENTS.md` 为准；待现场审计和基础修复完成后再重写本文。

## 一、整体架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              main.py (入口)                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  CLI: setup | start | sync                                        │   │
│  │  ↓                                                                │   │
│  │  create_context() → AppContext                                    │   │
│  │  ↓                                                                │   │
│  │  execute(action, context) → 顺序执行 Pipeline                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │  setup   │   │  start   │   │   sync   │
              │ (初始化) │   │ (启动)   │   │ (同步)   │
              └──────────┘   └──────────┘   └──────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
        ┌──────────────────────────────────────────────────────────────┐
        │                      Plugin Pipeline                          │
        │  ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐
        │  │ System │  Git   │ Torch  │ Comfy  │Userdata│ Nodes  │ Models │
        │  │ Addon  │ Addon  │ Addon  │ Addon  │ Addon  │ Addon  │ Addon  │
        │  └────────┴────────┴────────┴────────┴────────┴────────┴────────┘
        │     ①        ②        ③        ④        ⑤        ⑥        ⑦    │
        │                   (sync 动作按 ⑦→① 逆序执行)                     │
        └──────────────────────────────────────────────────────────────┘
```

---

## 二、三个核心命令

| 命令 | 作用 | 执行顺序 | Artifacts |
|------|------|----------|-----------|
| **`setup`** | 初始化整个环境（安装工具、ComfyUI、配置软链接等） | 顺序执行 ①→⑦ | **写入**并持久化到 `.artifacts.json` |
| **`start`** | 启动 ComfyUI 服务 | 顺序执行 ①→⑦ | **读取**已持久化的 artifacts |
| **`sync`** | 同步状态到 Git，生成 model-lock.yaml | **逆序**执行 ⑦→① | **读取**已持久化的 artifacts |

### 命令执行流程

```python
# main.py 核心逻辑
def main():
    # 1. 清理残留进程
    kill_process_by_name("python.*src.main", exclude_pid=os.getpid())
    
    # 2. setup 时清除网络缓存，确保走完整初始化
    if action == "setup":
        invalidate_network_cache()
    
    # 3. 初始化网络环境（代理 + 镜像 + Token）
    setup_network()
    
    # 4. 创建上下文（start/sync 需加载已持久化的 artifacts）
    load_artifacts = action in ("start", "sync")
    context = create_context(debug, load_artifacts)
    
    # 5. sync 阶段特殊处理：先同步代理配置
    if action == "sync":
        sync_proxy_config()
    
    # 6. 执行 Pipeline
    execute(action, context)
```

---

## 三、插件系统架构

### 3.1 核心组件关系

```
┌─────────────────────────────────────────────────────────────────┐
│                         AppContext                               │
│  ┌─────────────┬───────────────┬─────────────┬─────────────────┐ │
│  │ project_root│   base_dir    │  comfy_dir  │ addon_manifests │ │
│  │  (项目根)   │ (数据盘/tmp)  │ (系统盘)    │   (预加载配置)  │ │
│  ├─────────────┼───────────────┼─────────────┼─────────────────┤ │
│  │ cmd: ICommandRunner         │ state: IStateManager           │ │
│  │ (命令执行)                  │ (状态持久化)                   │ │
│  ├─────────────────────────────┴─────────────────────────────────┤ │
│  │               artifacts: Artifacts (强类型 DTO)               │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ comfy_dir | custom_nodes_dir | models_dir | proxy_url  │  │ │
│  │  │ uv_bin    | torch_installed  | cuda_version | ...       │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 注入到每个插件
                                    ▼
                    ┌───────────────────────────────┐
                    │          BaseAddon            │
                    │  ┌─────────────────────────┐  │
                    │  │ module_dir = "xxx"      │  │
                    │  │ name → module_dir       │  │
                    │  ├─────────────────────────┤  │
                    │  │ @hookimpl setup()       │  │
                    │  │ @hookimpl start()       │  │
                    │  │ @hookimpl sync()        │  │
                    │  └─────────────────────────┘  │
                    └───────────────────────────────┘
```

### 3.2 依赖注入与端口隔离

```
┌──────────────────────────────────────────────────────────────────┐
│                         Ports (接口)                              │
│  ┌────────────────────────┐  ┌────────────────────────┐          │
│  │     ICommandRunner     │  │     IStateManager      │          │
│  │  ─────────────────────│  │  ─────────────────────│          │
│  │  run(cmd, ...)        │  │  is_completed(key)    │          │
│  │  run_realtime(cmd)    │  │  mark_completed(key)  │          │
│  └───────────┬────────────┘  └───────────┬────────────┘          │
└──────────────┼───────────────────────────┼───────────────────────┘
               │                           │
               ▼                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Adapters (实现)                             │
│  ┌────────────────────────┐  ┌────────────────────────┐          │
│  │   SubprocessRunner     │  │   FileStateManager     │          │
│  │  (subprocess.run)      │  │  (YAML 文件存储)       │          │
│  └────────────────────────┘  └────────────────────────┘          │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 插件执行流程

```python
def execute(action, context, until, only):
    pipeline = create_pipeline()  # [System, Git, Torch, Comfy, Userdata, Nodes, Model]
    
    # sync 逆序执行
    if action == "sync":
        pipeline = list(reversed(pipeline))
    
    # 顺序执行每个插件的对应钩子
    for addon in pipeline:
        method = getattr(addon, action, None)  # setup/start/sync
        if method:
            method(context)
        
        if until and addon.name == until:
            break
    
    # setup 完成后持久化 artifacts
    if action == "setup":
        context.artifacts.save(context.project_root)
```

---

## 四、插件依赖关系图

```
                          ┌──────────────┐
                          │ SystemAddon  │ ① 基础设施
                          │ (uv, 缓存)   │
                          └──────┬───────┘
                                 │ artifacts.uv_bin
                                 ▼
                          ┌──────────────┐
                          │  GitAddon    │ ② Git/SSH 配置
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │ TorchAddon   │ ③ PyTorch CUDA
                          └──────┬───────┘
                                 │ artifacts.torch_installed
                                 ▼
                          ┌──────────────┐
                          │ ComfyAddon   │ ④ ComfyUI 核心
                          │              │   ← 依赖 uv_bin
                          └──────┬───────┘
                                 │ artifacts.comfy_dir
                                 │ artifacts.custom_nodes_dir
                                 │ artifacts.user_dir
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │UserdataAddon │ │ NodesAddon   │ │ ModelAddon   │
           │⑤ 用户数据    │ │⑥ 自定义节点  │ │⑦ 模型管理    │
           │← comfy_dir   │ │← comfy_dir   │ │← comfy_dir   │
           └──────────────┘ │← user_dir    │ └──────────────┘
                            └──────────────┘
```

---

## 五、设计亮点

### 5.1 强类型 Artifacts（跨进程共享）

```python
@dataclass
class Artifacts:
    """插件间共享的强类型数据容器"""
    
    # 每个插件的输出都有明确类型
    comfy_dir: Optional[Path] = None
    uv_bin: Optional[Path] = None
    torch_installed: bool = False
    
    # 支持持久化（setup → start → sync 跨进程）
    def save(self, project_root: Path) -> None: ...
    def load(cls, project_root: Path) -> "Artifacts": ...
```

**优势**：
- 编译时类型检查
- IDE 自动补全
- 强制声明插件的输入/输出契约

### 5.2 幂等性保障

```python
# 每个插件的 setup() 都通过 StateManager 保证幂等
if ctx.state.is_completed(StateKey.COMFY_INSTALLED):
    logger.info("  -> [SKIP] 已完成")
    return

# ... 执行安装逻辑 ...

ctx.state.mark_completed(StateKey.COMFY_INSTALLED)
```

### 5.3 端口/适配器模式（依赖倒置）

```python
# 接口定义（ports.py）
class ICommandRunner(ABC):
    @abstractmethod
    def run(self, cmd, ...) -> CommandResult: ...

# 实现（adapters.py）
class SubprocessRunner(ICommandRunner):
    def run(self, cmd, ...):
        return subprocess.run(...)

# 注入使用（插件中）
ctx.cmd.run(["comfy", "install"], check=True)
```

**优势**：便于测试（可 Mock），便于替换实现。

### 5.4 显式 Pipeline（无隐式依赖）

```python
# main.py:create_pipeline()
# 顺序硬编码，依赖关系一目了然
return [
    SystemAddon(),    # ① 无依赖
    GitAddon(),       # ② 无依赖
    TorchAddon(),     # ③ 无依赖
    ComfyAddon(),     # ④ 依赖 ① (uv_bin)
    UserdataAddon(),  # ⑤ 依赖 ④ (comfy_dir)
    NodesAddon(),     # ⑥ 依赖 ④ (comfy_dir, user_dir)
    ModelAddon(),     # ⑦ 依赖 ④ (comfy_dir)
]
```

---

## 六、目录结构总结

```
src/
├── main.py                 # 入口 & 生命周期调度
├── core/                   # 核心抽象层
│   ├── interface.py        # AppContext, BaseAddon, hookimpl
│   ├── artifacts.py        # 跨插件共享的强类型 DTO
│   ├── schema.py           # StateKey, EnvKey 枚举
│   ├── ports.py            # 接口：ICommandRunner, IStateManager
│   └── adapters.py         # 实现：SubprocessRunner, FileStateManager
├── addons/                 # 插件模块
│   ├── system/             # ① UV, 缓存迁移
│   ├── git_config/         # ② Git/SSH 配置
│   ├── torch_engine/       # ③ PyTorch CUDA
│   ├── comfy_core/         # ④ ComfyUI 核心安装
│   ├── userdata/           # ⑤ 用户数据软链接
│   ├── nodes/              # ⑥ 自定义节点管理
│   └── models/             # ⑦ 模型目录管理
└── lib/                    # 可复用库
    ├── download/           # 策略模式下载器
    ├── network/            # 代理 & 镜像管理
    └── utils.py            # 通用工具函数
```

---

## 七、设计模式总结

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **插件模式 (pluggy)** | `BaseAddon` + `@hookimpl` | 可扩展的插件架构 |
| **端口-适配器模式** | `ICommandRunner` / `IStateManager` | 依赖倒置，便于测试 |
| **组合根模式** | `AppContext` | 所有依赖在入口组装 |
| **策略模式** | `lib/download/` | 多种下载策略可切换 |
| **DTO 模式** | `Artifacts` | 强类型跨进程数据共享 |
| **幂等设计** | `StateManager` + `StateKey` | 重复执行安全 |

---

这是一个设计良好的 **插件化编排系统**，核心思想是：
1. **显式优于隐式** — Pipeline 顺序硬编码，依赖关系清晰
2. **强类型契约** — Artifacts 强制声明插件的输入输出
3. **关注点分离** — core（抽象）/ addons（插件）/ lib（复用库）职责明确
