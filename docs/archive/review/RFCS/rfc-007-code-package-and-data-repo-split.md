# RFC-007: 代码包发布与用户数据仓库拆分

## 背景

当前 README 的快速开始要求在 `/root/autodl-tmp` clone `autodl-instance` 代码仓，然后在代码仓内维护 `my-comfyui-backup`。这让工具源码、运行时状态、用户数据、sync 产物共享同一个工作目录。

这与长期目标冲突：工具代码应该可发布、可版本化、可升级；用户只需要安装工具，并维护自己的数据仓库。

## 用户价值

Job-to-be-done：新 AutoDL 实例上，用户只想恢复个人 ComfyUI 工作站，而不是维护工具源码 checkout。

拆分后：
- 新实例恢复路径变短：安装工具 → 绑定数据 repo → setup/start。
- 工具升级有版本边界：可 pin、可回滚、可发布 hotfix。
- 用户数据 repo 更干净：只包含 workflow、配置、snapshot、model-lock、mihomo 等个人资产。
- 降低误提交风险：工具源码变更不会混入用户数据 commit。

## 当前耦合点

主要耦合不是 Git 本身，而是 `project_root` 同时承担了三种含义：

| 当前位置 | 耦合 |
|---------|------|
| `README.md` | 要求 clone code repo 才能使用 |
| `init.sh` | 假设从源码目录执行 `python -m src.main setup` |
| `src/main.py:create_context()` | `project_root = Path(__file__).resolve().parent.parent`，等同源码根 |
| `src/main.py:load_manifests()` | 从 `project_root/src/addons` 和 `project_root/src/lib` 读取配置 |
| `SystemAddon._generate_bin_scripts()` | bin script 固定 `cd /root/autodl-tmp/autodl-instance` |
| `UserdataAddon` | `data_dir = ctx.project_root / my-comfyui-backup` |
| `src/status.py` | status/doctor 固定从 `project_root/my-comfyui-backup` 诊断 |
| `src/addons/models/config.py` | `model-lock.yaml` 固定写入 `project_root/my-comfyui-backup` |
| `src/lib/network/manager.py` | mihomo backup 目录隐式依赖 `my-comfyui-backup` 位置 |
| `scripts/sync_clash_profile.py` | 默认 repo dir 是源码根下的 `my-comfyui-backup` |

## 提议

MVP 目标：先把“代码根”和“用户数据根”拆开，再做发布。

### 1. 路径模型

引入明确路径语义：

| 名称 | 语义 | 推荐默认值 |
|------|------|------------|
| `code_root` | 已安装工具的 package/resource 根，只读 | Python package 内部 |
| `base_dir` | AutoDL 数据盘根 | `/root/autodl-tmp` |
| `workspace_dir` | 工具运行态目录，放 artifacts/log/state | `/root/autodl-tmp/autodl-workspace` |
| `userdata_dir` | 用户数据 repo 本地路径 | `/root/autodl-tmp/my-comfyui-backup` |
| `comfy_dir` | ComfyUI 安装目录 | `/root/ComfyUI` |
| `models_dir` | 大模型本体目录 | `/root/autodl-tmp/models` |

`project_root` 不再作为用户数据位置。保留时也只能表示 code/resource root，避免继续一词多义。

### 2. 数据 repo contract

`my-comfyui-backup` 应该只承载用户资产：

```text
my-comfyui-backup/
  user/
  script_examples/
  mihomo/
  model-lock.yaml
  snapshots or user/__manager__/snapshots/
  .autodl-instance/
    data-schema-version
    tool-version
    config.yaml
```

不放工具源码、不放 venv、不放 `src/`、不放 release build 产物、不放 secrets。

`.autodl-instance/config.yaml` 可保存非敏感配置，例如 sync dirs、模型目录、上次使用的工具版本。Token、SSH private key、subscription URL 仍通过环境变量、本机 secret file 或手动配置解决。

### 3. 安装形态

根据 uv 官方文档，适合工具发布的路径不是泛泛的 `uv install`，而是：
- `uv tool install <package>`：用户级安装 CLI tool。
- `uvx` / `uv tool run`：一次性运行某个已发布工具。
- `uv build` / `uv publish`：构建并发布 package。

参考：
- https://docs.astral.sh/uv/guides/tools/
- https://docs.astral.sh/uv/guides/package/
- https://docs.astral.sh/uv/concepts/projects/config/

目标命令形态：

```bash
uv tool install autodl-instance
autodl init --userdata-repo git@github.com:user/my-comfyui-backup.git
autodl setup
autodl start
autodl bye
autodl model status
autodl doctor
```

短命令 `start` / `bye` / `model` 可以作为兼容 shim 继续生成，但主入口应该收敛到一个 `autodl` CLI，降低全局命令污染。

### 4. 迁移阶段

Phase 1：路径抽象，不改用户体验
- `AppContext` 增加 `code_root`、`workspace_dir`、`userdata_dir`。
- 旧字段 `project_root` 暂时保留，但停止新增依赖。
- 所有 `my-comfyui-backup` 路径改为通过 `ctx.userdata_dir` 或 helper 获取。
- `status` / `doctor` 支持显式传入 `userdata_dir`。
- 测试覆盖“code repo 下数据”和“外部数据 repo”两种布局。

Phase 2：配置与 bootstrap 解耦
- 新增 `autodl init`，负责创建 workspace、clone/绑定 userdata repo、写入本地配置。
- 本地配置放在 `workspace_dir/config.yaml` 或 `~/.config/autodl-instance/config.yaml`。
- `src/addons/*/manifest.yaml` 只保留工具默认值；用户覆盖项不再要求编辑源码目录。

Phase 3：Python package 化
- 新增 `pyproject.toml`，定义 package metadata、dependencies、console scripts。
- 将 CLI 入口从 `python -m src.main` 迁到稳定 console script。
- 明确 package data：manifest、example 数据、脚本模板需要随 wheel 分发。
- 发布前验证 `uv build --no-sources` 和安装后 CLI smoke test。

Phase 4：兼容迁移
- 如果检测到旧布局 `/root/autodl-tmp/autodl-instance/my-comfyui-backup`，提示迁移到 `/root/autodl-tmp/my-comfyui-backup`。
- 迁移必须用户确认；不自动删除旧目录。
- 兼容读取旧 lock/config 一段时间，但新写入只写新位置。

## 非目标

- 不把模型本体纳入 Git。
- 不让 `model-lock.yaml` 变成自动下载任务源。
- 不做跨平台抽象；路径仍按 AutoDL root Linux 设计。
- 不引入 Web UI 或后台服务。
- 不要求用户把 secrets 提交到数据 repo。

## 替代方案

方案 A：继续 clone code repo 使用。
成本最低，但工具升级和用户数据生命周期继续混在一起，越往后越难拆。

方案 B：只移动 `my-comfyui-backup` 到 code repo 外。
能解决误提交，但没有解决发布、版本、CLI 入口和配置覆盖问题。

方案 C：一次性完成 package + migration + release。
看起来快，但风险集中：路径、配置、安装、sync 失败语义、文档会同时变化，不利于回滚。

本 RFC 选择分阶段：先路径语义，再 bootstrap，再 package。

## 影响面

- `AppContext` / `create_context`
- `load_manifests`
- `SystemAddon._generate_bin_scripts`
- `UserdataAddon`
- `ModelAddon` / `models.config`
- `status.py`
- `network.manager`
- `scripts/sync_clash_profile.py`
- `README.md`
- tests/unit + tests/integration
- 新增 `pyproject.toml` 与 package data 配置

## 风险

- 路径迁移最容易造成“sync 成功但写错 repo”。必须用测试覆盖。
- package 后不能再依赖源码相对路径读取配置；manifest/example 必须作为 package data。
- `uv tool install` 的 tool venv 不应被手动 mutate；ComfyUI、models、userdata 不能装进 tool venv。
- 用户可能已习惯直接编辑 `src/addons/*/manifest.yaml`；需要清晰迁移到本地 config。
- 旧 `start` / `bye` 命令如果立即移除会破坏肌肉记忆，应保留 shim。

## 验收标准

- 不 clone `autodl-instance` 源码也能完成一次新实例 setup。
- `my-comfyui-backup` 可放在 `/root/autodl-tmp/my-comfyui-backup`，不在 code root 下。
- `model-lock.yaml`、mihomo config、node snapshot、userdata sync 全部写入同一个 `userdata_dir`。
- `status` / `doctor` 能显示当前 code version、userdata repo、workspace dir。
- 旧布局仍能运行，并提示迁移路径。
- 全量 `pytest tests/ -q` 通过。
- 不引入自动模型下载。

## 测试计划

Unit：
- `create_context` 路径注入。
- userdata dir resolver：默认、新 config、旧布局兼容。
- model lock path 使用 `userdata_dir`。
- status/doctor 在外部 userdata repo 下输出正确。
- manifest/resource loader 在 package/resource 模式下能读取默认配置。

Integration：
- 源码布局 smoke：旧 `./init.sh` 仍可用。
- 外部数据布局 smoke：`code_root != userdata_dir.parent` 时 setup/sync 可用。
- 模拟旧路径迁移：只读检测和提示，不自动删除。
- Git push 失败仍保持 critical failure。

Packaging：
- `uv build --no-sources`。
- wheel 安装后运行 `autodl --help`、`autodl status`、`autodl doctor`。
- console scripts 不依赖当前工作目录。

## 开放问题

1. 包名用 `autodl-instance` 还是更明确的 `autodl-comfy`？
2. 主 CLI 是否统一为 `autodl`，还是保留 `start` / `bye` / `model` 作为第一等命令？
3. 本地配置放 `workspace_dir/config.yaml` 还是 `~/.config/autodl-instance/config.yaml`？
4. 是否允许 data repo 记录期望工具版本，并在启动时 warning “当前工具版本与数据 repo 期望不一致”？
5. 发布目标是 PyPI、GitHub release wheel，还是仅支持 `uv tool install git+https://...`？

## RICE

Reach 3/week, Impact 5, Confidence 0.8, Effort 4d => 3.0

虽然 RICE 不如前几个恢复链路修复高，但它解除的是长期架构耦合，是后续稳定发布、升级和迁移的前置条件。
